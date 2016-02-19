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

#from tecontroller.res.path import IPNetPath
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

lineend = "-"*100+'\n'

class MyGraphProvider(SouthboundManager):
    """This class overrwides the received_initial_graph abstract method of
    the SouthboundManager class. It is used to receive the initial
    graph from the Fibbing controller.

    The HAS_INITIAL_GRAPH is set when the method is called.

    """
    def __init__(self):
        super(MyGraphProvider, self).__init__()
    
    def received_initial_graph(self):
        super(MyGraphProvider, self).received_initial_graph()
        HAS_INITIAL_GRAPH.set()        

                
class LBController(DatabaseHandler):
    def __init__(self):
        """It basically reads the network topology from the MyGraphProvider,
        which is running in another thread because
        SouthboundManager.run() is blocking.
        
        Here we are assuming that the topology does not change.

        """
        super(LBController, self).__init__()
        self.flow_allocation = {} # {prefixA: {flow1:[path1, path2], flow2:[path2]},
                                  #  prefixB: {flow1:[path3], flow2:[path2]}}
                                  
        self.eventQueue = eventQueue #From where to read events 
        self.thread_handlers = {} #Used to schedule flow
                                  #alloc. removals

        self._stop = threading.Event() #Used to stop the thread
        self.hosts_to_ip = {}
        self.routers_to_ip = {}

        self.demands = set()
        
        CFG.read(dconf.C1_Cfg) #Must be called before create instance
                               #of SouthboundManager

        # Start the Southbound manager in a different thread    
        self.sbmanager = MyGraphProvider()
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
        jl = JsonListener(self.eventQueue)
        jl.start()
        log.info("LBC: Json listener thread created\n")

        
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
                bw = self.db.interface_bandwidth(xname, yname)
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
            log.info(lineend)
            log.info("LBC: NEW event in the queue ")
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
        # Get the destination network prefix
        dst_prefix = flow['dst'].network

        # Get the default OSFP Dijkstra path
        defaultPath = self.getDefaultDijkstraPath(self.network_graph, flow)
        
        # If it can be allocated, no Fibbing is needed
        if self.canAllocateFlow(flow, defaultPath):
            # Allocate new flow and default path to destination prefix
            self.addAllocationEntry(dst_prefix, flow, [defaultPath])
        else:
            # Otherwise, call the abstract method
            self.flowAllocationAlgorithm(dst_prefix, flow, defaultPath)            

    def getDefaultDijkstraPath(self, network_graph, flow):
        """Returns an list of network nodes representing the default Dijkstra
        path given the flow and a network graph.

        """        
        # We assume here that Flow is well formed, and that the
        # interface addresses of the hosts are given.
        src_name = self._db_getNameFromIP(flow['src'].compressed)
        src_router_name, src_router_id = self._db_getConnectedRouter(src_name)
        dst_network = flow['dst'].network.compressed

        # We take only routers in the route
        route = nx.dijkstra_path(network_graph, src_router_id, dst_network)
        route = [r for r in route if r in self.routers_to_ip.values()]
        
        return route

    def canAllocateFlow(self, flow, path):
        """Returns true if there is at least flow.size bandwidth available in
        all links along the path from flow.src to src.dst,

        """
        return self.getMinCapacity(path) >= flow.size


    def getEdgesInfoFromRoute(self, route):
        """Given a list of network nodes, returns a dictionary with the edges
        information.
        """
        edges = {(x, y): data for (x, y, data) in
                          self.network_graph.edges(data=True) if x in
                          route and y in route and
                          abs(route.index(x)-route.index(y)) == 1}
        return edges

    
    def getMinCapacity(self, path):
        """Returns the minimum capacity of the edges along the path.
        
        :param path: List of network nodes defining a path [A, B, C, D]"""
        caps_in_path = []
        for i in range(len(path)-1):
            edge_data = self.network_graph.get_edge_data(path[i], path[i+1])
            if 'capacity' not in edge_data.keys():
                # It enters here because it considers as edges the
                # links between interfaces (ip's) of the routers
                pass
            else:
                caps_in_path.append(edge_data['capacity'])
        return min(caps_in_path)


    def getMinCapacityEdge(self, path):
        """Returns the edge with the minimum capacity along the path.

        :param path: List of network nodes defining a path [A, B, C,
        D]

        """
        edges_in_path = [((path[i], path[i+1]),
                          self.network_graph.get_edge_data(path[i],
                                                           path[i+1])['capacity']) for i in
                         range(len(path)-1) if 'capacity' in
                         self.network_graph.get_edge_data(path[i],
                                                          path[i+1]).keys()]
        if edges_in_path:
            minim_c = edges_in_path[0][1]
            minim_edge = edges_in_path[0][0]
            for ((x,y), c) in edges_in_path:
                if c < minim_c:
                    minim_c = c
                    minim_edge = (x,y)
            return minim_edge
        else:
            raise StandardError("%s has no edges!"%str(path))

    def removePrefixLies(self, prefix):
        """Remove lies for a given prefix only if there are no more flows
        allocated for that prefix.
        """
        # Get the lies for prefix
        lsa = self.getLiesFromPrefix(prefix)
        if lsa:
            # Fibbed prefix
            # Let's check if there are other flows for prefix fist
            allocated_flows = self.getAllocatedFlows(prefix)
            if allocated_flows == []:
                self.sbmanager.remove_lsa(lsa)
                self.sbmanager.refresh_augmented_topo()
                log.info("LBC: removed lies for prefix: %s\n"%(str(prefix)))
                log.info("     LSAs: %s\n"%(str(lsa)))
            else:
                # Do not remove lsas yet. Other flows ongoing
                flows = [f for (f, p) in allocated_flows]
                log.info("LBC: lies for prefix %s not removed. Flows yet ongoing:\n"%(str(prefix)))
                for f in flows:
                    log.info("    %s\n"%(str(f)))
        else:
            # Prefix not fibbed
            log.info("LBC: removePrefixLies(): no lies for prefix: %s\n"%(str(prefix)))

    def getAllocatedFlows(self, prefix):
        """
        Given a prefix, returns a list of tuples:
        [(flow, path_list), (flow, path_list), ...]
        """
        if prefix in self.flow_allocation.keys():
            return [(f, p_l) for f, p_l in self.flow_allocation[prefix].iteritems()]
        else:
            log.info("LBC: getAllocatedFlows(): prefix %s not in flow_allocation table\n"%(str(prefix)))

    def getLiesFromPrefix(self, prefix):
        """Retrieves the LSA of the associated prefix from the southbound
        manager.
        """
        lsa_set = self.sbmanager.advertized_lsa.copy()
        while lsa_set != set():
            lsa = lsa_set.pop()
            dst = lsa.dest
            if prefix.compressed == dst:
                return lsa
        return None
        
    def addAllocationEntry(self, prefix, flow, path_list):
        """Add entry in the flow_allocation table.
        
        :param prefix: is a IPv4Network type

        :param path_list: List of paths (IPNetPath) for which this flow will be
                          multi-pathed towards destination prefix:
                          [[A, B, C], [A, D, C]]"""
        
        if prefix not in self.flow_allocation.keys():
            # prefix not in table
            self.flow_allocation[prefix] = {flow : path_list}
        else:
            if flow in self.flow_allocation[prefix].keys():
                self.flow_allocation[prefix][flow] += path_list
            else:
                self.flow_allocation[prefix][flow] = path_list
            
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info(lineend)
        log.info(("LBC: Flow ALLOCATED to Path - %s ")%t)
        log.info("      * dst_prefix: %s\n"%str(prefix.compressed))
        log.info("      * Paths (%d): %s\n"%(len(path_list), str([path for path in path_list])))
        log.info("      * Flow: %s\n"%str(flow))
        
        # Substract flow size from edges capacity
        # Check first how many ECMP paths are there
        ecmp_paths = float(len(path_list))
        for path in path_list:
            # Iterate through the graph
            for (x, y, data) in self.network_graph.edges(data=True):
                # If edge from path found in graph 
                if x in path and y in path and abs(path.index(x)-path.index(y))==1:
                    if 'capacity' not in data.keys():
                        #It enters here because it considers as edges the
                        #links between interfaces (ip's) of the routers
                        pass
                    else:
                        # Substract corresponding size
                        data['capacity'] -= (flow.size/ecmp_paths)

        # Define the removeAllocationEntry thread
        t = threading.Thread(target=self.removeAllocationEntry, args=(prefix, flow, path_list))
        # Add handler to list and start thread
        self.thread_handlers[flow] = t
        t.start()
        
    def removeAllocationEntry(self, prefix, flow, path_list):        
        """
        Removes the flow from the allocation entry prefix and restores the corresponding.
        """
        time.sleep(flow['duration']) #wait for after seconds
        
        if prefix not in self.flow_allocation.keys():
            # prefix not in table
            raise KeyError("The is no such prefix allocated: %s"%str(prefix.compressed))
        else:
            if flow in self.flow_allocation[prefix].keys():
                self.flow_allocation[prefix].pop(flow, None)
            else:
                raise KeyError("%s is not alloacated in this prefix %s"%str(repr(flow)))

        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info(lineend)
        log.info("LBC: Flow REMOVED from Path - %s "%t)
        log.info("      * dst_prefix: %s\n"%str(prefix.compressed))
        log.info("      * Paths (%d): %s\n"%(len(path_list), str([path for path in path_list])))
        log.info("      * Flow: %s\n"%repr(flow))

        # Add again flow size from edges capacity
        ecmp_paths = float(len(path_list))
        for path in path_list:
            for (x, y, data) in self.network_graph.edges(data=True):
                if x in path and y in path and abs(path.index(x)-path.index(y))==1:
                    if 'capacity' not in data.keys():
                        #pass: it enters here because it considers as edges
                        #the links between interfaces (ip's) of the routers
                        pass
                    else:
                        data['capacity'] += (flow.size/ecmp_paths)

        # Remove the lies for the given prefix
        self.removePrefixLies(prefix)
        
                        
    def getNetworkWithoutEdge(self, network_graph, x, y):
        """Returns a nx.DiGraph representing the network graph without the
        (x,y) edge. x and y must be nodes of network_graph.

        """
        ng_temp = copy.deepcopy(network_graph)
        ng_temp.remove_edge(x, y)
        return ng_temp


    def getAllPaths(self, network_graph, x, y):
        """Returns an ordered list representing all paths between node x and
        y in network_graph. Paths are ordered in increasing length.
        
        :param network_graph: networkx.DiGraph representing the network
        
        :param x,y: ipaddress.IPv4Network
        """
        pass

    def getNetworkWithoutFullEdges(self, network_graph, flow_size):
        """Returns a nx.DiGraph representing the network graph without the
        edge that can't allocate a flow of flow_size.
        
        :param flow_size: Attribute of a flow defining its size (in bytes).
        """
        ng_temp = copy.deepcopy(network_graph)
        
        full_edges = [ng_temp.remove_edge(x,y) for (x, y, data) in
                      network_graph.edges(data=True) if
                      data.get('capacity') and data.get('capacity') <=
                      flow_size]
        
        log.info("LBC: Edges that can't allocate flow of size: %d\n%s\n"%(flow_size, str(network_graph.difference(ng_temp))))

        return ng_temp

                    
                        
    @abc.abstractmethod
    def flowAllocationAlgorithm(self, dst_prefix, flow, initial_path):
        """
        """
        
class GreedyLBController(LBController):
    """Implements the flowAllocationAlgorithm of the
    LoadBalancerController by simply forcing simple path requirements
    in a greedy fashion.

    If a flow can't be allocated in the default Dijkstra path,
    flowAllocationAlgorithm is called. It removes all the edges of the
    network who can't support the newly created flow, and then
    computes a new path.

    After that, directs the Southbound manager to implement the
    corresponding DAG.

    If the flow can't be allocated in any path from source to
    destination, the algorithm falls back to the original dijsktra
    path and does not fib the network.
    """
    def __init__(self, *args, **kwargs):
        super(GreedyLBController, self).__init__(*args, **kwargs)


    def flowAllocationAlgorithm(self, dst_prefix, flow, initial_path):
        """
        Implements abstract method.
        """
        
        log.info("LBC: Greedy Algorithm started\n")
        start_time = time.time()
        i = 1

        # Remove edge that can't allocate flow from graph
        tmp_nw = self.getNetworkWithoutFullEdges(self.network_graph, flow['size'])
        try:
            # Calculate new default dijkstra path
            shortest_congestion_free_path = self.getDefaultDijkstraPath(tmp_nw, flow)

        except nx.NetworkXNoPath:
            # There is no congestion-free path between src and dst
            log.info("LBC: The flow can't be allocated in the network\n")
            log.info("     Allocating it the default Dijkstra path...\n")

            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, [initial_path])
            log.info("      * Dest_prefix: %s\n"%(str(dst_prefix.compressed)))
            log.info("      * Path: %s\n"%(str(initial_path)))

        else:
            log.info("LBC: Found path that can allocate flow\n")
            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, [shortest_congestion_free_path])
            # Call to FIBBING Controller should be here
            log.info("      * Dest_prefix: %s\n"%(str(dst_prefix.compressed)))
            log.info("      * Path: %s\n"%(str(shortest_congestion_free_path)))
            self.sbmanager.simple_path_requirement(dst_prefix.compressed,
                                                   [r for r in
                                                    shortest_congestion_free_path
                                                    if r in
                                                    self.routers_to_ip.values()])
            log.info("LBC: Fored forwarding DAG in Southbound Manager\n")

        # Do this allways
        elapsed_time = time.time() - start_time
        log.info("LBC: Greedy Algorithm Finished\n")
        log.info("      * Elapsed time: %ds\n"%elapsed_time)
        log.info("      * Iterations: %ds\n"%i)



class ECMPLBController(LBController):
    def __init__(self, *args, **kwargs):
        super(ECMPLBController, self).__init__(*args, **kwargs)

    def flowAllocationAlgorithm(self, dst_prefix, flow, initial_path):
        """
        Implements abstract method.
        """
        
        log.info("LBC: Greedy Algorithm started\n")
        start_time = time.time()
        i = 1

        # Remove edge that can't allocate flow from graph
        tmp_nw = self.getNetworkWithoutFullEdges(self.network_graph, flow['size'])
        try:
            # Calculate new default dijkstra path
            shortest_congestion_free_path = self.getDefaultDijkstraPath(tmp_nw, flow)

        except nx.NetworkXNoPath:
            # There is no congestion-free path between src and dst
            log.info("LBC: The flow can't be allocated in the network\n")
            log.info("     Allocating it the default Dijkstra path...\n")

            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, [initial_path])
            log.info("      * Dest_prefix: %s\n"%(str(dst_prefix.compressed)))
            log.info("      * Path: %s\n"%(str(initial_path)))

        else:
            log.info("LBC: Found path that can allocate flow\n")
            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, [shortest_congestion_free_path])
            # Call to FIBBING Controller should be here
            log.info("      * Dest_prefix: %s\n"%(str(dst_prefix.compressed)))
            log.info("      * Path: %s\n"%(str(shortest_congestion_free_path)))
            self.sbmanager.simple_path_requirement(dst_prefix.compressed,
                                                   [r for r in
                                                    shortest_congestion_free_path
                                                    if r in
                                                    self.routers_to_ip.values()])
            log.info("LBC: Fored forwarding DAG in Southbound Manager\n")
com
        # Do anyways
        elapsed_time = time.time() - start_time
        log.info("LBC: Greedy Algorithm Finished\n")
        log.info("      * Elapsed time: %ds\n"%elapsed_time)
        log.info("      * Iterations: %ds\n"%i)


if __name__ == '__main__':
    log.info("LOAD BALANCER CONTROLLER\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    lb = GreedyLBController()
    lb.run()
