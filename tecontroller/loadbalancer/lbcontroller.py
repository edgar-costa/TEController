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
from tecontroller.res import path

import networkx as nx
import threading
import subprocess
import ipaddress
import shared
import sched
import time
import abc

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


    def _db_getIPFromHostName(self, hostname):
        """Given the hostname of the host/host subnet, it returns the ip address
        of the interface in the hosts side. It is obtained from TopoDB

        It can also be called with a router name i.e: 'r1'
        """
        values = self.db.network[hostname]
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
                if isinstance(val, dict) and 'ip' in val.keys():
                    rname = key
                    return self.db.subnet(hostname, rname)
        else:
            raise TypeError("Routers can't")


    def _db_getConnectedRouter(self, hostname):
        """Get connected router information from hostname given its name.

        """
        hostinfo = [values for name, values in
                    self.db.network.iteritems() if name == hostname
                    and values['type'] != 'router'][0]
        if hostinfo is not None:
            for key, val in hostinfo.iteritems():
                if isinstance(val, dict) and 'ip' in val.keys():
                    router_name = key
                    router_id = self._db_getIPFromHostName(router_name)
                    return router_name, router_id


                
class LBController(DatabaseHandler):

    def __init__(self):
        """It basically reads the network topology from the MyGraphProvider,
        which is running in another thread because
        SouthboundManager.run() is blocking.
        
        Here we are assuming that the topology does not change.

        """
        super(LBController, self).__init__()
        self.flow_allocation = {} # {(srcA, dstB): {path1: [flow1,flow2,...], path2},
                                  #  (srcC, dstD): {path1: [flow3, flow6]}}
                                  
        self.eventQueue = shared.eventQueue #From where to read events 
        self.timer_handlers = [] #threading.Timer() #Used to schedule
                                 #flow alloc. removals
        self._stop = threading.Event() #Used to stop the thread
        self.hosts_to_ip = {}
        self.routers_to_ip = {}
        self.scheduler = sched.scheduler(time.time, time.sleep)
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

        # Fill the host2Ip and router2ip attributes
        self._createHost2IPBindings()
        self._createRouter2IPBindings()

        
        #spawn Json listener thread
        #lbc_lf = open(lbcontroller_logfile, 'w')
        #subprocess.Popen(['./jsonlistener.py'], stdin=None,
        #                 stdout=lbc_lf, stderr=lbc_lf)
        #lbc_lf.close()


    def getPathFromFlow(self, flow):
        """
        """
        pass

    def getFlowListFromPath(self, path):
        """
        """
        pass

        
    def _readBwDataFromDB(self):
        """Introduces BW data from /tmp/db.topo into the network DiGraph and
        sets the capacity to the link bandwidth.
        """
        for (x, y, data) in self.network_graph.edges(data=True):
            if 'C' in x or 'C' in y: # means is the controller...
                continue
            xname = self._db_getNameFromIP(x)
            yname = self._db_getNameFromIP(y)
            if xname and yname:
                bw = self.db.bandwidth(xname, yname)
                data['bw'] = bw
                data['capacity'] = bw
        
    def _createHost2IPBindings(self):
        """Fills the dictionary self.hosts_to_ip with the corresponding
        name-ip pairs
        """
        for node_ip in self.network_graph.nodes():
            if not self.network_graph.is_controller(node_ip) and not self.network_graph.is_router(node_ip):
                name = self._db_getNameFromIP(node_ip)
                if name:
                    ip_iface_host = self._db_getIPFromHostName(name)
                    ip_iface_router = self._db_getSubnetFromHostName(name)
                    router_name, router_id = self._db_getConnectedRouter(name) 
                    self.hosts_to_ip[name] = {'iface_host': ip_iface_host,
                                              'iface_router': ip_iface_router,
                                              'router_name': router_name,
                                              'router_id': router_id}

    def _createRouter2IPBindings(self):
        """Fills the dictionary self.routers_to_ip with the corresponding
        name-ip pairs
        """
        for node_ip in self.network_graph.nodes():
            if self.network_graph.is_router(node_ip):
                name = self._db_getNameFromIP(node_ip)
                self.routers_to_ip[name] = node_ip



     def getNodeName(self, ip):
        """Returns the name of the host/or subnet of hosts, given the IP.
        """
        name = [name for name, values in
                self.hostName2IpSubnet.iteritems() if ip in
                values.values()][0]
        return name
    
    
    def getEdgeBw(self, x, y):
        """
        Returns the total bandwidth of the network edge between x and y
        """
        return self.network_graph.get_edge_data(x,y)['bw']
    

    def getEdgeCapacity(self, x, y):
        """Returns the capacity of the network edge between x and y
        """
        return self.network_graph.get_edge_data(x,y)['capacity']

    
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
                self.dealWithNewFlow(flow)
            else:
                print "Unknown Event:"
                print event
                
    def dealWithNewFlow(self, flow):
        """
        Treat new incoming flow.
        """
        defaultPath = self.getDefaultDijkstraPath(flow)
        
        if self.canAllocateFlow(defaultPath, flow):
            self.addFlowToPath(defaultPath, flow)
        else:
            self.flowAllocationAlgorithm(flow)            

    def getDefaultDijkstraPath(self, flow):
        """Gives the current path from src to dest
        """
        
        pass

    def canAllocateFlow(self, path, flow):
        """Returns true if there is at least flow.size bandwidth available in
        all links along the path from flow.src to src.dst,

        """
        return self.getMinCapacity(path) >= flow.size


    def getMinCapacity(self, path):
        """
        """
        pass
    
    def addFlowToPath(self, path, flow):
        """
        """
        pass

            
class GreedyLBController(LBController):
    def __init__(self, *args, **kwargs):
        super(GreedyLBControllerLB, self).__init__(*args, **kwargs)

    
    def flowAllocationAlgorithm(self, flow):
        """
        Implements abstract method
        """
        pass
        







"""
 # Create the key entries for the flow_allocation data structure
 self._createInitialPaths()


    def _createInitialPaths(self):
        all_pairs = nx.all_pairs_dijkstra_path(self.network_graph)
        for src, data in all_pairs.iteritems():
            for dst, route in data.iteritems():
                edge_data = {}
                for i, v in enumerate(route):
                    if i<len(route)-1:
                        edge_data[(route[i], route[i+1])] = self.network_graph.get_edge_data(route[i], route[i+1])
                new_path = path.Path(src=src, dst=dst, route=route, edges=edge_data)
                d = {}
                d[new_path] = []
                self.flow_allocation[(src, dst)] = d

"""
