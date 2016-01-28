#!/usr/bin/python

"""Implements a flow-based load balancer using Fibbing. 

Is built upon the Northbound controller, and balances the load of the
network in terms of forwarding DAGs between source-destination pairs.

Receives flow demands from the custom built Traffic Generator, through
a Json-Rest interface.

"""

from fibbingnode.algorithms.southbound_interface import SouthboundManager
from fibbingnode.misc.igp_graph import IGPGraph

from fibbingnode.misc.mininetlib.ipnet import TopologyDB
from fibbingnode import CFG

from tecontroller.res import defaultconf as dconf

import networkx as nx
import threading
import subprocess
import ipaddress
import shared

HAS_INITIAL_GRAPH = threading.Event()

lbcontroller_logfile = dconf.Hosts_LogFolder + "LBC_json.log"

class MyGraphProvider(SouthboundManager):
    """This class overrwides the received_initial_graph abstract method of
    the SouthboundManager class. It is used to receive the initial
    graph from the Fibbing controller.

    The HAS_INITIAL_GRAPH is set when the method is called.

    """
    def received_initial_graph(self):
        HAS_INITIAL_GRAPH.set()        


class DatabaseHandler(object):
    def __init__(self):
        # Read the topology info from DB_Path
        self.db = TopologyDB(db=dconf.DB_Path)

    def _db_getNameFromIP(self, x):
        """Returns the name of the host or the router given the ip of the
        router or the ip of the router's interface towards that
        subnet.
        """
        if x.find('/') == -1: # it means x is a router id
            ip_router = ipaddress.ip_address(x)
            name = [name for name, values in
                    self.db.network.iteritems() if values['type'] ==
                    'router' and
                    ipaddress.ip_address(values['routerid']) ==
                    ip_router][0]
            return name
        
        elif 'C' not in x: # it means x is an interface ip and not the
                           # weird C_0
            ip_iface = ipaddress.ip_interface(x)
            for name, values in self.db.network.iteritems():
                if values['type'] != 'router':
                    for key, val in values.iteritems():    
                        if isinstance(val, dict):
                            ip_iface2 = ipaddress.ip_interface(val['ip'])
                            if ip_iface.network == ip_iface2.network:
                                return name

    def _db_getIPDBFromHostName(self, name):
        """Given the name of the host/host subnet, it returns the ip address
        of the interface in the hosts side. It is obtained from TopoDB

        """
        values = self.db.network[name]
        if values['type'] == 'router':
            return ipaddress.ip_address(values['routerid']).compressed
        else:
            ip = [ipaddress.ip_interface(v['ip']) for v in
                  values.values() if isinstance(v, dict)][0]
            return ip.compressed
        
    def _db_getSubnetFromHostName(self, hostname):
        """Given the hostname of a host (e.g 's1'), returns the subnet address
        in which it is connected.
        """
        hostinfo = [values for name, values in
                    self.db.network.iteritems() if name == hostname
                    and values['type'] != 'router'][0]
        
        if hostinfo is not None:
            for key, val in hostinfo.iteritems():
                if isinstance(val, dict) and 'ip' in val.values():
                    rname = key
                    return self.db.subnet(hostname, rname)
        else:
            raise TypeError("Routers can't")
                
            
class LBController(DatabaseHandler):

    def __init__(self):
        """It basically reads the network topology from the MyGraphProvider,
        which is running in another thread because
        SouthboundManager.run() is blocking.
        
        Here we are assuming that the topology does not change.

        """
        super(LBController, self).__init__()
        self.flow_allocation = {}
        self.eventQueue = shared.eventQueue #From where to read events 
        self.timer_handlers = [] #threading.Timer() #Used to schedule
                                 #flow alloc. removals
        self._stop = threading.Event() #Used to stop the thread
        self.hostsName2IpSubnet = {}
        
        CFG.read(dconf.C1_Cfg) #Must be called before create instance
                               #of SouthboundManager

        sbmanager = MyGraphProvider()
        t = threading.Thread(target=sbmanager.run, name="Graph Listener")
        t.start()

        HAS_INITIAL_GRAPH.wait() #Blocks until initial graph arrives

        # Retreieve network from Fibbing Controller
        self.network_graph = sbmanager.igp_graph

        # Include BW data inside network graph
        self._readBwDataFromDB()

        # Fill the name2Ip attribute
        self._createName2IpBindings()
        
        #spawn Json listener thread
        #lbc_lf = open(lbcontroller_logfile, 'w')
        #subprocess.Popen(['./jsonlistener.py'], stdin=None,
        #                 stdout=lbc_lf, stderr=lbc_lf)
        #lbc_lf.close()
        
    def _readBwDataFromDB(self):
        """Introduces BW data from /tmp/db.topo into the network DiGraph

        """
        for (x, y, data) in self.network_graph.edges(data=True):
            if 'C' in x or 'C' in y: # means is the controller...
                continue
            xname = self._db_getNameFromIP(x)
            yname = self._db_getNameFromIP(y)
            if xname and yname:
                data['bw'] = self.db.bandwidth(xname, yname)
        
    def _createName2IpBindings(self):
        """Fills the dictionary self.name2Ip with the corresponding name-ip
        pairs
        """
        for node_ip in self.network_graph.nodes():
            if not self.network_graph.is_controller(node_ip) and not self.network_graph.is_router(node_ip):
                name = self._db_getNameFromIP(node_ip)
                if name:
                    ip_iface_host = self._db_getIPDBFromHostName(name)
                    ip_iface_router = self._db_getSubnetFromHostName(name)
                    self.hostsName2IpSubnet[name] = {'iface_host': ip_iface_host,
                                                     'iface_router': ip_iface_router}
                
    def getNodeName(self, ip):
        pass
                
                
    def getEdgeBw(self, x, y):
        """
        Returns the total bandwidth of the link between x and y
        """
        return self.network_graph.get_edge_data(x,y)['bw']
    
        
    def stop(self):
        """Stop the LBController correctly
        """
        #Here we should deal with the handlers of the spawned threads
        #and subprocesses...
        self._stop.set()

    def isStopped(self):
        """Check if LBController is set to be stopped or not
        """
        return self._stop.isSet()

    def run():
        """Main loop that deals with new incoming events
        """
        while not self.isStopped():
            
            #Wait until there's something in the queue
            while self.eventQueue.empty(): 
                pass
        
            event = self.eventQueue.get() #Should be blocking?
            if event['type'] == 'newFlowStarted':
                flow = event['data']
                self.dealWithNewFlow(flow, algorithm='greedy')
            else:
                print "Unknown Event:"
                print event



                
    def assignFlowToPath(self, flow, path):
        pass

    def removeFlowFromPath(self, flow, path):
        pass

    def deletePathFromGraph(self, path):
        pass
    
    def dealWithNewFlow(self, flow):
        currentPath = self.getCurrentPath(flow.src, flow.dst)
        if self.canAllocateFlow(currentPath, flow):
            updateFlowAllocationTable(currentPath, flow)
        else:
            path = self.getNewCongestionFreePath(flow)            

    def getCurrentPath(self, src, dst):
        """Gives the current path from src to dest
        """
        pass

    def canAllocateFlow(self, path, flow):
        """Returns true if there is at least flow.size bandwidth available in
        all links along the path from flow.src to src.dst,

        """
        pass
    
    def updateFlowAllocationTable(path, flow):
        if path in self.flow_allocation.keys():
            self.flow_allocation[path].append(flow)
        else:
            self.flow_allocation[path] = [flow]

            
class GreedyLBController(LBController):
    def __init__(self, *args, **kwargs):
        super(GreedyLBControllerLB, self).__init__(*args, **kwargs)

    



