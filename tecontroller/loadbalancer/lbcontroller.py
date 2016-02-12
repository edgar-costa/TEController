#!/usr/bin/python

"""Implements a flow-based load balancer using Fibbing. 

Is built upon the Northbound controller, and balances the load of the
network in terms of forwarding DAGs between source-destination pairs.

Receives flow demands from the custom built Traffic Generator, through
a Json-Rest interface.

"""
from fibbingnode.algorithms.southbound_interface import SouthboundManager
from fibbingnode.misc.igp_graph import IGPGraph
from fibbingnode.misc.mininetlib import get_logger
from fibbingnode import CFG

from tecontroller.res import defaultconf as dconf
from tecontroller.res.dbhandler import DatabaseHandler

from tecontroller.res.path import IPNetPath
from tecontroller.res.flow import Flow
from tecontroller.loadbalancer.jsonlistener import JsonListener

import networkx as nx
import threading
import subprocess
import ipaddress
import sched
import time
import abc
import traceback
import Queue
import copy

HAS_INITIAL_GRAPH = threading.Event()

lbcontroller_logfile = dconf.Hosts_LogFolder + "LBC_json.log"

log = get_logger()

eventQueue = Queue.Queue()

lineend = "-"*60+'\n'


class MyGraphProvider(SouthboundManager):
    """This class overrwides the received_initial_graph abstract method of
    the SouthboundManager class. It is used to receive the initial
    graph from the Fibbing controller.

    The HAS_INITIAL_GRAPH is set when the method is called.

    """
    def received_initial_graph(self):
        HAS_INITIAL_GRAPH.set()        

                
class LBController(DatabaseHandler):
    def __init__(self):
        """It basically reads the network topology from the MyGraphProvider,
        which is running in another thread because
        SouthboundManager.run() is blocking.
        
        Here we are assuming that the topology does not change.

        """
        super(LBController, self).__init__()
        self.flow_allocation = {} # {(route1): [flow1,flow2],
                                  #  (route2): [flow3, flow6]}
                                  
        self.eventQueue = eventQueue #From where to read events 
        self.thread_handlers = {} #threading.Timer() #Used to schedule
                                 #flow alloc. removals
        self._stop = threading.Event() #Used to stop the thread
        self.hosts_to_ip = {}
        self.routers_to_ip = {}
        #self.scheduler = sched.scheduler(time.time, time.sleep)
        CFG.read(dconf.C1_Cfg) #Must be called before create instance
                               #of SouthboundManager

        self.sbmanager = MyGraphProvider()

        # Wait a bit more please...
        time.sleep(dconf.Hosts_InitialWaitingTime)

        t = threading.Thread(target=self.sbmanager.run, name="Graph Listener")
        t.start()
        log.info("LBC: Graph Listener thread started\n")

        HAS_INITIAL_GRAPH.wait() #Blocks until initial graph arrives
        log.info("LBC: Initial graph received\n")
                 
        # Retreieve network from Fibbing Controller
        self.network_graph = self.sbmanager.igp_graph
        
        # Include BW data inside network graph
        self._readBwDataFromDB()
        if not self._bwInAllEdges():
            self._readBwDataFromDB()

        log.info("LBC: Bandwidths written in network_graph\n")

        # Fill the host2Ip and router2ip attributes
        self._createHost2IPBindings()
        self._createRouter2IPBindings()
        log.info("LBC: Created IP-names bindings\n")
        for name, data in self.hosts_to_ip.iteritems():
            log.info("    Hostname: %s --> %s:%s\n"%(name,data['router_name'], data['router_id']))

        #spawn Json listener thread
        jl = JsonListener(eventQueue)
        jl.start()
        log.info("LBC: Json listener thread created\n")
        
        #lbc_lf = open(lbcontroller_logfile, 'w')
        #try:
        #    subprocess.Popen([dconf.LBC_Path+'jsonlistener.py'], stdin=None,
        #                     stdout=lbc_lf, stderr=lbc_lf)
        #    
        #    lbc_lf.close()    
        #except Exception:
        #    log.info("LOG: ERROR spawning jsonlistener.py\n")                     
        #log.info(traceback.print_exc())

    def getRouteFromFlow(self, flow):
        """
        """
        path = [route for route, data in
                self.flow_allocation.iteritems() if flow in
                data]
        if path != []:
            return path[0]
        else:
            return []

    def getFlowListFromRoute(self, path):
        """
        """
        flowlist = [data for route, data in
                    self.flow_allocation.iteritems() if route ==
                    path.route]
        
        if flowlist != []:
            return flowlist[0]
        else:
            return []

        
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
                data['bw'] = int(bw*1e6)
                data['capacity'] = int(bw*1e6)

            else:
                log.info("LBC: ERROR -> _readBwDataFromDB(self): did not find xname and yname")
                
    def _bwInAllEdges(self):
        ep = [True if 'capacity' in data.keys() and 'bw' in data.keys() else False for (x, y, data) in self.network_graph.edges(data=True)]
        return False not in ep
                
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

    def run(self):
        """Main loop that deals with new incoming events
        """
        while not self.isStopped():
            event = self.eventQueue.get()
            log.info("LBC: NEW event in the queue "+lineend)
            log.info("      * Type: %s\n"%event['type'])
            #log.info("LBC:  * Data: %s)\n"%repr(event['data']))
            
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
        # Get the default OSFP Dijkstra path
        defaultPath = self.getDefaultDijkstraPath(self.network_graph, flow)

        # If it can be allocated, no Fibbing is needed
        if self.canAllocateFlow(defaultPath, flow):
            self.addFlowToPath(defaultPath, flow)
        else:
            # Otherwise, call the abstract method
            self.flowAllocationAlgorithm(flow, defaultPath)            

    def getDefaultDijkstraPath(self, network_graph, flow):
        """Gives the current path from src to dest
        """
        # We assume here that Flow is well formed, and that the
        # interface addresses of the hosts are given.
        src_name = self._db_getNameFromIP(flow['src'].compressed)
        src_router_name, src_router_id = self._db_getConnectedRouter(src_name)
        dst_network = flow['dst'].network.compressed
        
        route = tuple(nx.dijkstra_path(network_graph, src_router_id, dst_network))
        edges = self.getEdgesInfoFromRoute(route)
        path = IPNetPath(route=route, edges=edges)
        return path

    def canAllocateFlow(self, path, flow):
        """Returns true if there is at least flow.size bandwidth available in
        all links along the path from flow.src to src.dst,

        """
        return self.getMinCapacity(path) >= flow.size


    def getEdgesInfoFromRoute(self, route):
        """
        """
        edges = {(x, y): data for (x, y, data) in
                          self.network_graph.edges(data=True) if x in
                          route and y in route and
                          abs(route.index(x)-route.index(y)) == 1}
        return edges

    
    def getMinCapacity(self, path):
        """Returns the capacity of the lowest-capacity edge along the path.
        """
        #        edges_in_path = [self.network_graph.get_edge_data(path.route[i],
        #                        path.route[i+1])['capacity'] for i in
        #                        range(len(path)-1)]
        #log.info("\n\nLBC: Entered in getMinCapacity\n")
        #log.info("LBC:  - Path: %s\n"%str(path))
        #log.info("LBC:  - NetGraph: %s\n\n"%str(self.network_graph.edges(data=True)))
        
        caps_in_path = []
        for i in range(len(path.route)-1):
            edge_data = self.network_graph.get_edge_data(path.route[i], path.route[i+1])
            if 'capacity' not in edge_data.keys():
                #log.info("LBC: ERROR: capacity not in edge_data:\n")
                #log.info("LBC: (%s, %s):%s\n"%(path.route[i], path.route[i+1], str(edge_data)))

                #pass: it enters here because it considers as edges
                #the links between interfaces (ip's) of the routers
                pass

            else:
                caps_in_path.append(edge_data['capacity'])
        return min(caps_in_path)


    def getMinCapacityEdge(self, path):
        """Returns the capacity of the lowest-capacity edge along the path.
        """
        edges_in_path = [((path.route[i], path.route[i+1]),
                          self.network_graph.get_edge_data(path.route[i],
                                                           path.route[i+1])['capacity']) for i in
                         range(len(path)-1)]
        if edges_in_path:
            minim_c = edges_in_path[0][1]
            minim_edge = edges_in_path[0][0]
            for ((x,y), c) in edges_in_path:
                if c < minim_c:
                    minim_c = c
                    minim_edge = (x,y)
            return minim_edge
        
    def addFlowToPath(self, path, flow):
        """
        """
        if path.route in self.flow_allocation.keys(): #exists already
            self.flow_allocation[path.route].append(flow)
        else:
            self.flow_allocation[path.route] = [flow]

        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info(("LBC: Flow ALLOCATED to Path - %s "+lineend)%t)
        log.info("      * Path: %s\n"%str(path.route))
        log.info("      * Flow: %s\n"%str(flow))
        
        # Substract flow size from edges capacity
        for (x, y, data) in self.network_graph.edges(data=True):
            if x in path.route and y in path.route and abs(path.route.index(x)-path.route.index(y))==1:
                if 'capacity' not in data.keys():
                    #log.info("LBC: (addFlowToPath): capacity not in keys:\n")
                    #log.info("LBC:   * (x, y): (%s, %s)\n"%(str(x), str(y)))
                    #log.info("LBC:   * data: %s\n"%str(data))

                    #pass: it enters here because it considers as edges
                    #the links between interfaces (ip's) of the routers
                    pass
                else:
                    data['capacity'] -= flow.size

        t = threading.Thread(target=self.removeFlowFromPath, args=(path, flow, flow['duration']))
        self.thread_handlers[flow] = t
        t.start()
        # Schedule flow removal
        #self.scheduler.enter(flow['duration'], 1, self.removeFlowFromPath, ([path, flow]))
        #self.scheduler.run()
        
    def removeFlowFromPath(self, path, flow, after):        
        """
        """
        time.sleep(after) #wait for after seconds
        
        if path.route in self.flow_allocation.keys(): #exists already
            self.flow_allocation[path.route].remove(flow)
        else:
            raise KeyError("The flow is not in the Path")

        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info(("LBC: Flow REMOVED from Path - %s "+lineend)%t)
        log.info("      * Path: %s\n"%str(path.route))
        log.info("      * Flow: %s\n"%repr(flow))

        # Add again flow size from edges capacity
        for (x, y, data) in self.network_graph.edges(data=True):
            if x in path.route and y in path.route and abs(path.route.index(x)-path.route.index(y))==1:
                if 'capacity' not in data.keys():
                    #log.info("LBC: (addFlowToPath): capacity not in keys:\n")
                    #log.info("LBC:   * (x, y): (%s, %s)\n"%(str(x), str(y)))
                    #log.info("LBC:   * data: %s\n"%str(data))

                    #pass: it enters here because it considers as edges
                    #the links between interfaces (ip's) of the routers
                    pass
                else:
                    data['capacity'] += flow.size

    def getNetworkWithoutEdge(self, network_graph, x, y):
        """Returns a nx.DiGraph representing the network graph without the
        (x,y) edge.

        """
        ng_temp = copy.deepcopy(network_graph)
        ng_temp.remove_edge(x, y)
        return ng_temp

        
                
    @abc.abstractmethod
    def flowAllocationAlgorithm(self, flow, initial_path):
        """
        """
        
class GreedyLBController(LBController):
    def __init__(self, *args, **kwargs):
        super(GreedyLBController, self).__init__(*args, **kwargs)

    def flowAllocationAlgorithm(self, flow, initial_path):
        """
        Implements abstract method.
        """
        log.info("LBC: Greedy Algorithm started\n")
        start_time = time.time()
        i = 1

        # Remove edge with least capacity from path
        (ex, ey) = self.getMinCapacityEdge(initial_path)
        tmp_nw = self.getNetworkWithoutEdge(self.network_graph, ex, ey)
        # Calculate new default dijkstra path
        next_default_dijkstra_path = self.getDefaultDijkstraPath(tmp_nw, flow)

        if tmp_nw.edges() == self.network_graph.edges():
            log.info("LBC: ERROR: copy of network graph is wrongly done \n")
        
        # Repeat it until path is found that can allocate flow
        while not self.canAllocateFlow(next_default_dijkstra_path, flow):
            i = i + 1
            initial_path = next_default_dijkstra_path
            (ex, ey) = self.getMinCapacityEdge(initial_path)
            tmp_nw = self.getNetworkWithoutEdge(tmp_nw, ex, ey)
            next_default_dijkstra_path = self.getDefaultDijkstraPath(tmp_nw, flow)

        # Allocate flow to Path
        self.addFlowToPath(next_default_dijkstra_path, flow)
        elapsed_time = time.time() - start_time 
        log.info("LBC: Greedy Algorithm Finished "+lineend)
        log.info("      * Elapsed time: %ds\n"%elapsed_time)
        log.info("      * Iterations: %ds\n"%i)

        # Call to FIBBING Controller should be here
        log.info("     * Destination: %s Network: %s\n"%(flow['dst'].compressed, flow['dst'].network.compressed))
        
        log.info("     * Path: %s\n"%(str(list(next_default_dijkstra_path.route)[:-1])))
        self.sbmanager.simple_path_requirement(flow['dst'].network.compressed,
                                               list(next_default_dijkstra_path.route)[:-1])
        log.info("LBC: Forcing forwarding DAG in Southbound Manager\n")
                 
if __name__ == '__main__':
    log.info("LOAD BALANCER CONTROLLER\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    lb = GreedyLBController()
    lb.run()

