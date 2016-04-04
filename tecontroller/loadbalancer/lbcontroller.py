#!/usr/bin/python
"""Implements a flow-based load balancer using Fibbing. 

Is built upon the Northbound controller, and balances the load of the
network in terms of forwarding DAGs between source-destination pairs.

Receives flow demands from the custom built Traffic Generator, through
a Json-Rest interface.
"""
from fibbingnode.algorithms.southbound_interface import SouthboundManager
from fibbingnode.misc.mininetlib import get_logger
from fibbingnode import CFG

from tecontroller.res import defaultconf as dconf
from tecontroller.res.dbhandler import DatabaseHandler

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
import sys

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
                
class LBController(object):
    def __init__(self):
        """It basically reads the network topology from the MyGraphProvider,
        which is running in another thread because
        SouthboundManager.run() is blocking.
        
        Here we are assuming that the topology does not change.
        """
        # Dictionary that keeps the allocation of the flows in the network paths
        self.flow_allocation = {} 
        # {prefixA: {flow1 : [path_list], flow2 : [path_list]},
        #  prefixB: {flow4 : [path_list], flow3 : [path_list]}}

        # Lock to make flow_allocation thread-safe
        self.flowAllocationLock = threading.Lock()
        
        # From where to read events 
        self.eventQueue = eventQueue
        
        # Used to schedule flow alloc. removals
        self.thread_handlers = {} 

        # Data structure that holds the current forwarding dags for
        # all advertised destinations in the network
        self.dagsLock = threading.Lock()
        self.dags = {}

        # Used to stop the thread
        self._stop = threading.Event() 

        # Object that handles the topology database
        self.db = DatabaseHandler()
    
        # Connects to the southbound controller. Must be called before
        # create instance of SouthboundManager
        CFG.read(dconf.C1_Cfg) 

        # Start the Southbound manager in a different thread.    
        self.sbmanager = MyGraphProvider()
        t = threading.Thread(target=self.sbmanager.run, name="Graph Listener")
        t.start()
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Graph Listener thread started\n"%t)

        # Blocks until initial graph arrived notification is received
        # from southbound manager
        HAS_INITIAL_GRAPH.wait() 
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Initial graph received\n"%t)

        # Retreieve network graph from southbound manager
        self.network_graph = self.sbmanager.igp_graph

        # Mantains the list of the network prefixes advertised by the OSPF routers
        self.ospf_prefixes = self._fillInitialOSPFPrefixes()
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Initial OSPF prefixes read\n"%t)
        
        # Include BW data inside the initial graph.
        n_router_links = self._countRouter2RouterEdges()
        self._readBwDataFromDB()
        i = 0
        while not self._bwInAllRouterEdges(n_router_links):
            i += 1
            time.sleep(1)
            self._readBwDataFromDB()            
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Bandwidths written in network_graph after %d iterations\n"%(t,i))

        # Read the initial graph. We keep this as a copy of the
        # physical topology. In initial graph, the instantaneous
        # capacities of the links are kept.
        self.initial_graph = self.network_graph.copy()
        
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Created IP-names bindings\n"%t)
        log.info("\tHostname\tip\tsubnet\n")
        for name, data in self.db.hosts_to_ip.iteritems():
            log.info("\t%s\t%s\t%s\n"%(name, data['iface_host'], data['iface_router']))

        log.info("\tRouter name\tip\t\n")
        for name, ip in self.db.routers_to_ip.iteritems():
            log.info("\t%s\t%s\n"%(name, ip))

        # Create here the initial DAGS for each destination in the
        # network
        self._createInitialDags()
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Initial DAGS created\n"%t)

        # Spawn Json listener thread
        jl = JsonListener(self.eventQueue)
        jl.start()
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Json listener thread created\n"%t)

    def run(self):
        """Main loop that deals with new incoming events
        """
        while not self.isStopped():
            # Get event from the queue (blocking)
            event = self.eventQueue.get()
            log.info(lineend)
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - run(): NEW event in the queue\n"%t)
            log.info("\t* Type: %s\n"%event['type'])
            
            if event['type'] == 'newFlowStarted':
                # Fetch flow from queue
                flow = event['data']
                log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))

                # We assume that upon dealing with a new flow, the
                # self.dags is not accessed by any other thread
                with self.dagsLock:
                    with self.flowAllocationLock:
                        # Deal with new flow
                        self.dealWithNewFlow(flow)
                
            else:
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - run(): UNKNOWN Event\n"%t)
                log.info("\t* Event: "%str(event))

    def dealWithNewFlow(self, flow):
        """Called when a new flow arrives. This method should be overwritten
        by each of the subclasses performing the various algorithms.

        When this function is called, no algorithm to allocate flows
        is called. The LBController only keeps track of the default
        allocations of the flows.
        """
        # In general, this won't be True that often...
        ecmp = False
        
        # Get the communicating interfaces
        src_iface = flow['src']
        dst_iface = flow['dst']

        # Get host ip's
        src_ip = src_iface.ip
        dst_ip = dst_iface.ip

        # Get their correspoding networks
        src_network = src_iface.network
        dst_network = self.getCurrentOSPFPrefix(dst_iface.compressed)

        # Get the string-type prefixes        
        src_prefix = src_network.compressed
        dst_prefix = dst_network.compressed

        # Get the current path from source to destination
        currentPaths = self.getActivePaths(src_iface, dst_iface, dst_prefix)

        if len(currentPaths) > 1:
            # ECMP is happening
            ecmp = True
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): ECMP is ACTIVE\n"%t)
        elif len(currentPaths) == 1:
            ecmp = False
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): ECMP is NOT active\n"%t)
        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): ERROR\n"%t)

        # Detect if flow is going to create congestion
        if self.canAllocateFlow(flow, currentPaths):
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): Flow can be ALLOCATED\n"%t)

        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): Flow will cause CONGESTION\n"%t)

        # We just allocate the flow to the currentPaths
        self.addAllocationEntry(dst_prefix, flow, currentPaths)

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
  
    def _readBwDataFromDB(self):
        """Introduces BW data from /tmp/db.topo into the network DiGraph and
        sets the capacity to the link bandwidth.
        """
        for (x, y, data) in self.network_graph.edges(data=True):
            if 'C' in x or 'C' in y: # means is the controller...
                continue

            
            if self.network_graph.is_router(x) and self.network_graph.is_router(y):
                # Fill edges between routers only!
                xname = self.db.getNameFromIP(x)
                yname = self.db.getNameFromIP(y)
                if xname and yname:
                    try:
                        bw = self.db.interface_bandwidth(xname, yname)
                        data['bw'] = int(bw*1e6)
                        data['capacity'] = int(bw*1e6)
                    except:
                        import ipdb; ipdb.set_trace()
                        print "EXCEPTION"
                        print x,y
                        print xname, yname
                else:
                    t = time.strftime("%H:%M:%S", time.gmtime())
                    log.info("%s - _readBwDataFromDB(): ERROR: did not find %s (%s) and %s (%s)\n"%(t, x, xname, y, yname))

                
    def _countRouter2RouterEdges(self):
        """
        Counts how many unidirectional links between routers exist in the network
        """
        routers = [n for (n, data) in self.db.network.iteritems() if data['type'] == 'router']
        edges_count = 0
        for r in routers:
            data = self.db.network[r]
            for n, d in data.iteritems():
                if type(d) == dict:
                    try:
                        self.db.routerid(n)
                    except TypeError:
                        pass
                    else:
                        edges_count +=1
        return edges_count

    def _countWrittenBw(self):
        ep = [1 if 'capacity' in data.keys() and 'bw' in
              data.keys() else 0 for (x, y, data) in
              self.network_graph.edges(data=True) if
              self.network_graph.is_router(x) and
              self.network_graph.is_router(y)]
        return sum(ep)

    def _bwInAllRouterEdges(self, n_router_links):
        current_count = self._countWrittenBw()
        return current_count == n_router_links and current_count != 0

    def _fillInitialOSPFPrefixes(self):
        """
        Fills up the data structure
        """
        prefixes = []
        for prefix in self.network_graph.prefixes:
            prefixes.append(ipaddress.ip_network(prefix))
        return prefixes

    def getCurrentOSPFPrefix(self, interface_ip):
        """Given a interface ip address of a host in the mininet network,
        returns the longest prefix currently being advertised by the
        OSPF routers.

        :param interface_ip: string representing a host's interface ip
                             address. E.g: '192.168.233.254/30'

        Returns: an ipaddress.IPv4Network object
        """
        iface = ipaddress.ip_interface(interface_ip)
        iface_nw = iface.network
        iface_ip = iface.ip
        longest_match = (None, 0)
        for prefix in self.ospf_prefixes:
            prefix_len = prefix.prefixlen
            if iface_ip in prefix and prefix_len > longest_match[1]:
                longest_match = (prefix, prefix_len)
        return longest_match[0]

    def getCurrentDag(self, dst):
        """
        Returns a copy of the current DAG towards destination
        """
        return self.dags[dst].copy()

    def getInitialDag(self, dst):
        currentDag = self.getCurrentDag(dst)
        initialDag = currentDag.copy()
        
        # set fibbed edges to notactive and default-ones to active
        for (u, v, data) in currentDag.edges(data=True):
            if data['fibbed'] == True:
                initialDag.get_edge_data(u,v)['active'] = False
            else:
                initialDag.get_edge_data(u,v)['active'] = True
        return initialDag
        
    def setCurrentDag(self, dst, dag):
        """
        Sets the current DAG towards destination
        """
        self.dags[dst] = dag
        
    def getActiveEdges(self, dag, node):
        activeEdges = []
        for n, data in dag[node].iteritems():
            if data['active'] == True:
                activeEdges.append((node, n))
        return activeEdges

    def getFibbedEdges(self, dag, node):
        """
        Returns the fibbed edges in the
        """
        fibbedEdges = []
        for n, data in dag[node].iteritems():
            if data['fibbed'] == True:
                fibbedEdges.append((node, n))
        return fibbedEdges

    def getDefaultEdges(self, dag, node):
        """Returns the list of edges from node that are used by default in
        OSPF"""
        defaultEdges = []
        for n, data in dag[node].iteritems():
            if data['fibbed'] == False:
                defaultEdges.append((node, n))
        return defaultEdges

    def switchDagEdgesData(self, dag, path_list, **kwargs):
        """Sets the data of the edges in path_list to the attributes expressed
        in kwargs.

        :param dag: nx.DiGraph representing the dag of the destination
                    subnet that we want to change the edges state.

        :param path_list: list of paths. E.g: [[A,B,C],[A,G,C]...]

        :param **kwargs: Edge attributes to be set.

        """
        # Check first if we have a path_list or a edges_list
        if path_list != [] and isinstance(path_list[0], tuple):
            # We have an edges list
            edge_list = path_list
                        
        elif path_list != [] and isinstance(path_list[0], list):
            # We have a path_list
            edge_list = self.getEdgesFromPathList(path_list)
            
        if path_list != []:
            for (u,v) in edge_list:
                if (u,v) not in dag.edges():
                    # The initial edges will never get the fibbed
                    # attribute set to True, since they exist in the dag
                    # from the beginning.
                    dag.add_edge(u,v)
                    edge_data = dag.get_edge_data(u,v)
                    dag.get_edge_data(u,v)['fibbed'] = True

                # Do for all edges
                edge_data = dag.get_edge_data(u,v)
                for key, value in kwargs.iteritems():
                    edge_data[key] = value

        # Return modified dag when finished
        return dag

    def getActiveDag(self, dst):
        """Returns the DAG being currently deployed in practice for the given
        destination.
        """
        dag = self.dags[dst]
        active_dag = dag.copy()
        action = [active_dag.remove_edge(u,v) for (u,v, data) in
                  active_dag.edges(data=True) if data['active'] == False]
        return active_dag
    
    def getActivePaths(self, src_iface, dst_iface, dst_prefix):
        """Returns the current active path between two host interface ips and
        the destination prefix for which we want to retrieve the
        current active path.
        
        :param src_iface, dst_iface: ipaddres.ip_interface object

        :param dst_prefix: string representing the destination prefix
                           (i.e: 192.168.225.0/25).
        """
        # Get current active DAG for that destination
        active_dag = self.getActiveDag(dst_prefix)

        # Get src_iface and dst_iface attached routers
        routers = list(self.network_graph.routers)
        src_rid = None
        dst_rid = None

        for r in routers:
            if self.network_graph.has_successor(r, src_iface.network.compressed):
                d = src_iface.network.compressed
                if self.network_graph[r][d]['fake'] == False:
                    src_rid = r

            if self.network_graph.has_successor(r, dst_iface.network.compressed):
                d = dst_iface.network.compressed
                if self.network_graph[r][d]['fake'] == False:
                    dst_rid = r
                    
        if src_rid and dst_rid:
            # Calculate path and return it
            active_paths = self._getAllPathsLimDAG(active_dag, src_rid, dst_rid, 0)
            return active_paths
        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            to_print = "%s - getActivePaths(): No paths could be found between %s and %s for subnet prefix %s\n"
            log.info(to_print%(t, str(src_iface), str(dst_iface), dst_prefix))
            return [[]]
        
    def _createInitialDags(self):
        """Populates the self.dags attribute by creating a complete DAG for
        each destination.
        """
        # Log it
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Creating initial DAGs\n"%t)
        pairs_already_logged = []
                           
        apdp = nx.all_pairs_dijkstra_path(self.initial_graph, weight='metric')

        for prefix in self.network_graph.prefixes:
            dag = nx.DiGraph()

            # Get IP of the connected router
            cr = [r for r in self.network_graph.routers if self.network_graph.has_successor(r, prefix)][0]
            
            # Get subnet prefix
            subnet_prefix = prefix
            
            other_routers = [rn for rn in self.network_graph.routers if rn != cr]

            for r in other_routers:
                # Get the shortest path
                dpath = apdp[r][cr]
                
                # Are there possibly more paths with the same cost? Let's check:
                # Get length of the default dijkstra shortest path
                dlength = self.getPathLength(dpath+[subnet_prefix])

                # Get all paths with length equal to the defaul path length
                default_paths = self._getAllPathsLim(self.initial_graph, r, subnet_prefix, dlength)
                
                if len(default_paths) > 1:
                    # ECMP is happening
                    ecmp = True
                    if (cr, r) not in pairs_already_logged and (r, cr) not in pairs_already_logged:
                        to_print = "\tECMP is ACTIVE between %s and %s. There are %d paths with equal cost of %d\n"
                        log.info(to_print%(self.db.getNameFromIP(cr), self.db.getNameFromIP(r), len(default_paths), dlength))
                        pairs_already_logged.append((cr, r))
                    
                elif len(default_paths) == 1:
                    ecmp = False
                    default_paths = [dpath]

                else:
                    t = time.strftime("%H:%M:%S", time.gmtime())
                    log.info("%s - _createInitialDags(): ERROR. At least there should be a path\n"%t)
                    
                # Iterate through paths and add edges to DAG
                for path in default_paths:
                    edge_list = zip(path[:-1], path[1:])
                    for (u,v) in edge_list:
                        if self.network_graph.is_router(u) and self.network_graph.is_router(v):
                            dag.add_edge(u,v)
                            edge_data = dag.get_edge_data(u,v)
                            edge_data['active'] = True
                            edge_data['fibbed'] = False
                            edge_data['ongoing_flows'] = False

            # Add DAG to prefix
            self.dags[subnet_prefix] = dag
    
    def getEdgesFromPathList(self, path_list):
        """Given a list of paths, returns a list of all the edges contained
        in these paths.
        """
        edge_list = []
        for path in path_list:
            edge_list += zip(path[:-1], path[1:])
        return edge_list

    def isFibbed(self, dst_prefix):
        """Returns true if there exist fake LSA for that prefix in the
        network.

        TODO: probably must be changed...
        
        """
        return (self.getLiesFromPrefix(dst_prefix) != [])

    def isFibbedPath(self, dst_prefix, path):
        """Returns True if it finds a fibbed edge active along the path in
        dst_prefix DAG
        """
        currentDag = self.getCurrentDag(dst_prefix)        
        for (u,v) in zip(path[:-1], path[1:]):
            edge_data = currentDag.get_edge_data(u,v)
            if edge_data['fibbed'] == True and edge_data['active'] == True:
                # Fake edge found
                return True
        return False

    def addAllocationEntry(self, prefix, flow, path_list):
        """Add entry in the flow_allocation table.
        
        :param prefix: destination prefix. Expressed as an
                       IPv4Interface object
        
        :param path_list: List of paths for which this flow will be
                          multi-pathed towards destination prefix:
                          [[A, B, C], [A, D, C]]"""

        if prefix not in self.flow_allocation.keys():
                # prefix not in table
            self.flow_allocation[prefix] = {flow : path_list}
        else:
            self.flow_allocation[prefix][flow] = path_list
            
        # Loggin a bit...
        t = time.strftime("%H:%M:%S", time.gmtime())
        to_print = "%s - flow ALLOCATED to Paths\n"
        log.info(to_print%t)
        log.info("\t* Dest_prefix: %s\n"%prefix)
        log.info("\t* Paths (%s): %s\n"%(len(path_list), str([self.toLogRouterNames(path) for path in path_list])))
        log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))
                        
        # Check first how many ECMP paths are there
        ecmp_paths = float(len(path_list))

        # Current dag for destination
        current_dag = self.getCurrentDag(prefix)
        
        # Iterate the paths
        for path in path_list:
            # Calculate paths with only routers
            path_only_routers = [p for p in path if self.network_graph.is_router(p)]

            # Extract the edges of the path
            edges = zip(path_only_routers[:-1], path_only_routers[1:])
            
            # Modify first the current destination dag: ongoing_flows = True
            current_dag = self.switchDagEdgesData(current_dag, edges, ongoing_flows=True)
                        
            for (u, v) in edges:
                # Get capacity of the edge (u,v)
                data = self.initial_graph.get_edge_data(u, v)
                capacity = data.get('capacity', None)
                if capacity:
                    # Substract full flow size in edges of both paths 
                    data['capacity'] -= (flow.size)
                    
                    # Modify also the capacity data of the reverse edge
                    data_i = self.initial_graph.get_edge_data(v, u)
                    data_i['capacity'] = data['capacity']

                else:
                    to_print = "ERROR: capacity key not found in edge (%s, %s)\n"
                    log.info(to_print%(u, v))

        # Set the current dag
        self.setCurrentDag(prefix, current_dag)

        # Define the removeAllocatoinEntry thread
        t = threading.Thread(target=self.removeAllocationEntry, args=(prefix, flow))
        # Start the thread
        t.start()
        # Add handler to list and start thread
        self.thread_handlers[flow] = t
   
    def removeAllocationEntry(self, prefix, flow):
        """
        Removes the flow from the allocation entry prefix and restores the corresponding.
        """
        # Wait until flow finishes
        time.sleep(flow['duration']) 
        
        # Acquire locks for self.flow_allocation and self.dags
        # dictionaries
        self.flowAllocationLock.acquire()
        self.dagsLock.acquire()
        
        log.info(lineend)
        if prefix not in self.flow_allocation.keys():
            # prefix not in table
            raise KeyError("The is no such prefix allocated: %s"%str(prefix))
        else:
            if flow in self.flow_allocation[prefix].keys():
                path_list = self.flow_allocation[prefix].pop(flow, None)
            else:
                raise KeyError("%s is not alloacated in this prefix %s"%str(repr(flow)))

        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Flow REMOVED from Paths\n"%t)
        log.info("\t* Dest_prefix: %s\n"%prefix)
        log.info("\t* Paths (%s): %s\n"%(len(path_list), str([self.toLogRouterNames(path) for path in path_list])))
        log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))

        # Check first how many ECMP paths are there
        ecmp_paths = float(len(path_list))

        # Current dag for destination
        current_dag = self.getCurrentDag(prefix)
        
        # Get the active Dag
        activeDag = self.getActiveDag(prefix)
        log.info("\t* removeAllocationEntry: initial DAG\n\t  %s\n"%str(self.toLogDagNames(activeDag).edges()))
        
        # Get current remaining allocated flows for destination
        remaining_flows = self.getAllocatedFlows(prefix)

        # Acumulate edges for which there are flows ongoing
        ongoing_edge_list = []
        for (f, f_path_list) in remaining_flows:
            ongoing_edge_list += self.getEdgesFromPathList(f_path_list)
                
        # Iterate the path_list
        for path in path_list:
            # Get paths with only routers
            path_only_routers = [p for p in path if self.network_graph.is_router(p)]
            
            # Calculate edges of the path
            edges = zip(path_only_routers[:-1], path_only_routers[1:])
            
            # Calculate which of these edges can be set to ongoing_flows = False
            edges_without_flows = [(u, v) for (u, v) in edges if (u, v) not in ongoing_edge_list]
            
            # Set them
            current_dag = self.switchDagEdgesData(current_dag, edges_without_flows, ongoing_flows=False)
            
            # Now add back capacities to edges
            for (u, v) in edges:
                data = self.initial_graph.get_edge_data(u, v)
                capacity = data.get('capacity', None)
                if capacity:
                    # Add back the full capacity taken by the flow
                    # that just finished
                    data['capacity'] += (flow.size)
                    
                    # Set also the reverse edge
                    data_i = self.initial_graph.get_edge_data(v, u)
                    data_i['capacity'] = data['capacity']
                else:
                    to_print = "ERROR: capacity key not found in edge (%s, %s)\n"
                    log.info(to_print%(u, v))
                    
        # Set the new calculated dag to its destination prefix dag
        self.setCurrentDag(prefix, current_dag)
        
        # Remove the lies for the given prefix
        self.removePrefixLies(prefix, path_list)

        # Release locks
        self.flowAllocationLock.release()
        self.dagsLock.release()
        


        
    def removePrefixLies(self, prefix, path_list):
        """Remove lies for a given prefix only if there are no more flows
        allocated for that prefix flowing through some edge of
        path_list.

        :param prefix: subnet prefix

        :param path_list: List of paths from source to
                          destination. E.g: [[A,B,C],[A,D,C]]
        """
        # log a bit
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Removing existing lies...\n"%t)

        # Get the current DAG for that prefix
        current_dag = self.getCurrentDag(prefix)

        # Get the active Dag
        activeDag = self.getActiveDag(prefix)
        
        log.info("\t* removePrefixLies: initial DAG\n\t  %s\n"%str(self.toLogDagNames(activeDag).edges()))

        # Check if fibbed edge in paths
        thereIsFibbedPath = False
        for path in path_list:
            thereIsFibbedPath = thereIsFibbedPath or self.isFibbedPath(prefix, path)

        if not thereIsFibbedPath:
            # Paths for this flow are not fibbed
            to_print = "\t* No fibbed edges found in paths %s for prefix: %s\n"
            log.info(to_print%(str(self.toLogRouterNames(path_list)), prefix))

        else:
            # Get the lies for prefix
            lsa = self.getLiesFromPrefix(prefix)

            log.info("\t* Found fibbed edges in paths: %s\n"%str(self.toLogRouterNames(path_list)))

            # Fibbed prefix
            # Let's check if there are other flows for prefix fist
            allocated_flows = self.getAllocatedFlows(prefix)

            # Check if there are flows to prefix going through some
            # path in path_list. If not, we can delete the
            # lies. Otherwise, we must wait.
            if allocated_flows == []:
                log.info("\t* No allocated flows remain for prefix\n")
                # Obviously, if no flows are found, we can already
                # remove the lies.

                # Set the DAG for the prefix destination to its
                # original version
                path_list_edges = []
                for path in path_list:
                    path_list_edges += zip(path[:-1], path[1:])
            
                # Remove edges from initial paths
                for path in path_list:
                    for node in path:
                        # Set edges to initial situation (fibbed=True,
                        # active=False) and (fibbed=False, active=True)
                        default_edges = self.getDefaultEdges(current_dag, node)
                        current_dag = self.switchDagEdgesData(current_dag, default_edges, active=True)
                        
                        fibbed_edges = self.getFibbedEdges(current_dag, node)
                        current_dag = self.switchDagEdgesData(current_dag, fibbed_edges, active=False)

                # Set current Dag
                self.setCurrentDag(prefix, current_dag)

                # Get the active Dag
                activeDag = self.getActiveDag(prefix)
                
                log.info("\t* removePrefixLies: final DAG\n\t  %s\n"%str(self.toLogDagNames(activeDag).edges()))
                
                # Get the active Dag
                activeDag = self.getActiveDag(prefix)

                # Force it to fibbing
                self.sbmanager.add_dag_requirement(prefix, activeDag.copy())

                # Log it
                log.info("\t* Removed lies for prefix: %s\n"%prefix)
                log.info("\t* LSAs: %s\n"%(str(lsa)))
                
            else:
                log.info("\t* Some flows for prefix still remain ongoing\n")
                canRemoveLSA = True

                # Collect first the edges of the paths to remove
                path_edges_list = []
                for path in path_list:
                    path_edges_list += zip(path[:-1], path[1:])

                log.info("Edges of the paths to remove: %s\n"%self.toLogRouterNames(path_edges_list))
                for (flow, flow_path_list) in allocated_flows:
                    log.info("flow: %s, path: %s\n"%(self.toLogFlowNames(flow), self.toLogRouterNames(flow_path_list)))
                    # Get all edges used by flows sending to same
                    # destination prefix
                    flow_edges_list = []
                    for flow_path in flow_path_list:
                        flow_edges_list += zip(flow_path[:-1], flow_path[1:])

                    check = [True if (u,v) in path_edges_list else False for (u,v) in flow_edges_list]
                    log.info("CHECK list: %s\n"%str(check))
                    if sum(check) > 0:
                        # Do not remove lsas yet. Other flows ongoing
                        # in one of the paths in path_list
                        canRemoveLSA = False
                        break
                        
                if canRemoveLSA == False:
                    # Just log it
                    flows = [f for (f, p) in allocated_flows]
                    to_print = "\t* Lies for prefix %s not removed. Flows yet ongoing:\n"
                    log.info(to_print%prefix)
                    for f in flows:
                        log.info("\t\t%s\n"%(self.toLogFlowNames(f)))
                else:
                    # Set the DAG for the prefix destination to its
                    # original version
                    path_list_edges = []
                    for path in path_list:
                        path_list_edges += zip(path[:-1], path[1:])
            
                    # Remove edges from initial paths
                    for path in path_list:
                        for node in path:
                            # Set edges to initial situation (fibbed=True,
                            # active=False) and (fibbed=False, active=True)
                            default_edges = self.getDefaultEdges(current_dag, node)
                            current_dag = self.switchDagEdgesData(current_dag, default_edges, active=True)
                        
                            fibbed_edges = self.getFibbedEdges(current_dag, node)
                            current_dag = self.switchDagEdgesData(current_dag, fibbed_edges, active=False)

                    self.setCurrentDag(prefix, current_dag)
                
                    # Get the active Dag
                    activeDag = self.getActiveDag(prefix)

                    # Force it to fibbing
                    self.sbmanager.add_dag_requirement(prefix, activeDag.copy())
                
                    # Log it
                    log.info("\t* Removed lies for prefix: %s\n"%prefix)
                    log.info("\t* LSAs: %s\n"%(str(lsa)))

        log.info(lineend)
           
    def getDefaultDijkstraPath(self, network_graph, flow):
        """Returns an list of network nodes representing the default Dijkstra
        path given the flow and a network graph.

        """        
        # We assume here that Flow is well formed, and that the
        # interface addresses of the hosts are given.
        src_name = self.db.getNameFromIP(flow['src'].compressed)
        src_router_name, src_router_id = self.db.getConnectedRouter(src_name)
        dst_network = flow['dst'].network.compressed

        # We take only routers in the route
        route = nx.dijkstra_path(network_graph, src_router_id, dst_network, weight='metric')
        return route

    def getPathLength(self, path):
        """Given a path as a list of traversed routers, it returns the sum of
        the weights of the traversed links along the path.
        """
        routers = [n for n in path if self.initial_graph.is_router(n)]
        edges = [self.initial_graph.get_edge_data(u,v)['metric'] for
                 (u,v) in zip(path[:-1], path[1:])]
        return sum(edges)

    def canAllocateFlow(self, flow, path_list):
        """Returns true if there is at least flow.size bandwidth available in
        all links along the path (or multiple paths in case of ECMP)
        from flow.src to src.dst,
        """
        for path in path_list:
            if self.getMinCapacity(path) < flow.size:
                return False
        return True

    def getMinCapacity(self, path):
        """Returns the minimum capacity of the edges along the path.
        
        :param path: List of network nodes defining a path [A, B, C, D]"""
        caps_in_path = []
        for (u,v) in zip(path[:-1], path[1:]):
            edge_data = self.initial_graph.get_edge_data(u, v)
            cap = edge_data.get('capacity', None)
            caps_in_path.append(cap)
        try:
            mini = min(caps_in_path)
            return mini
        
        except ValueError:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - getMinCapacity(): ERROR: min could not be calculated\n"%t)
            log.info("\t* Path: %s\n"%path)            
            raise ValueError

    def getMinCapacityEdge(self, path):
        """Returns the edge with the minimum capacity along the path.

        :param path: List of network nodes defining a path [A, B, C,
        D]
        """
        edges_in_path = [((path[i], path[i+1]),
                          self.initial_graph.get_edge_data(path[i],
                                                           path[i+1])['capacity']) for i in
                         range(len(path)-1) if 'capacity' in
                         self.initial_graph.get_edge_data(path[i],
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
        
    def getAllocatedFlows(self, prefix):
        """
        Given a prefix, returns a list of tuples:
        [(flow, path), (flow, path), ...]
        """
        if prefix in self.flow_allocation.keys():
            return [(f, p) for f, p in self.flow_allocation[prefix].iteritems()]
        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            to_print = "%s - getAllocatedFlows(): WARNING: "
            to_print += "prefix %s not yet in flow_allocation table\n"
            log.info(to_print%(t, prefix))
            return []
        
    def getFlowSizes(self, prefix):
        """Returns the sum of flows with destination prefix, and how many
        flows there are
        """
        allocated_flows = self.getAllocatedFlows(prefix)
        sizes = [f['size'] for (f, p) in allocated_flows]
        return sum(a), len(a)
    
    def getLiesFromPrefix(self, prefix):
        """Retrieves the LSA of the associated prefix from the southbound
        manager.

        """
        lsa_set = self.sbmanager.advertized_lsa.copy()
        lsa_list = []
        while lsa_set != set():
            lsa = lsa_set.pop()
            dst = lsa.dest
            if prefix == dst:
                lsa_list.append(lsa)
        return lsa_list
        
    def getNetworkWithoutFullEdges(self, network_graph, flow_size):
        """Returns a nx.DiGraph representing the network graph without the
        edge that can't allocate a flow of flow_size.
        
        :param network_graph: IGPGraph representing the network.

        :param flow_size: Attribute of a flow defining its size (in bytes).
        """
        ng_temp = network_graph.copy()
        for (x, y, data) in network_graph.edges(data=True):
            cap = data.get('capacity')
            if cap and cap <= flow_size and self.network_graph.is_router(x) and self.network_graph.is_router(y):
                edge = (x, y)
                ng_temp.remove_edge(x, y) 
        return ng_temp
    
    def getAllPathsRanked(self, igp_graph, start, end, ranked_by='length'):
        """Recursive function that returns an ordered list representing all
        paths between node x and y in network_graph. Paths are ordered
        in increasing length.
        
        :param igp_graph: IGPGraph representing the network
        
        :param start: router if of source's connected router

        :param end: compressed subnet address of the destination
                    prefix."""
        paths = self._getAllPathsLim(igp_graph, start, end, 0)
        if ranked_by == 'length':
            ordered_paths = self._orderByLength(paths)
        elif ranked_by == 'capacity':
            ordered_paths = self._orderByCapacityLeft(paths)
        return ordered_paths
    
    def _getAllPathsLim(self, igp_graph, start, end, k, path=[], len_path=0, die=False):
        """Recursive function that finds all paths from start node to end
        node with maximum length of k.
        """
        if die == False:
            # Accumulate path length first
            if path == []:
                len_path = 0
            else:
                last_node = path[-1]
                len_path += igp_graph.get_edge_data(last_node, start)['metric']
                
            # Accumulate nodes in path
            path = path + [start]
        
            if start == end:
                # Arrived to the end. Go back returning everything
                if k == 0:
                    return [path]
                elif len_path < k+1:
                    return [path]
                else:
                    self._getAllPathsLim(igp_graph, start, end, k, path=path, len_path=len_path, die=True)
            
            if not start in igp_graph:
                return []

            paths = []
            for node in igp_graph[start]:
                if node not in path: # Ommiting loops here
                    if k == 0:
                        # If we do not want any length limit
                        newpaths = self._getAllPathsLim(igp_graph, node, end, k, path=path, len_path=len_path)
                        for newpath in newpaths:
                            paths.append(newpath)
                    elif len_path < k+1:
                        newpaths = self._getAllPathsLim(igp_graph, node, end, k, path=path, len_path=len_path)
                        for newpath in newpaths:
                            paths.append(newpath)
            return paths
        else:
            # Recursive call dies here
            pass

    def _getAllPathsLimDAG(self, dag, start, end, k, path=[]):
        """Recursive function that finds all paths from start node to end node
        with maximum length of k.

        If the function is called with k=0, returns all existing
        loopless paths between start and end nodes.

        :param dag: nx.DiGraph representing the current paths towards
                    a certain destination.

        :param start, end: string representing the ip address of the
                           star and end routers (or nodes) (i.e:
                           10.0.0.3).

        :param k: specified maximum path length (here means hops,
                  since the dags do not have weights).

        """
        # Accumulate nodes in path
        path = path + [start]
        
        if start == end:
            # Arrived to the end. Go back returning everything
            return [path]
            
        if not start in dag:
            return []

        paths = []
        for node in dag[start]:
            if node not in path: # Ommiting loops here
                if k == 0:
                    # If we do not want any length limit
                    newpaths = self._getAllPathsLimDAG(dag, node, end, k, path=path)
                    for newpath in newpaths:
                        paths.append(newpath)
                elif len(path) < k+1:
                    newpaths = self._getAllPathsLimDAG(dag, node, end, k, path=path)
                    for newpath in newpaths:
                        paths.append(newpath)
        return paths

    def _orderByLength(self, paths):
        """Given a list of arbitrary paths. It ranks them by lenght (or total
        edges weight).

        """
        # Search for path lengths
        ordered_paths = []
        for path in paths:
            pathlen = 0
            for (u,v) in zip(path[:-1], path[1:]):
                if self.network_graph.is_router(v):
                    pathlen += self.network_graph.get_edge_data(u,v)['metric']
            ordered_paths.append((path, pathlen))

        # Now rank them
        ordered_paths = sorted(ordered_paths, key=lambda x: x[1])
        return ordered_paths

    
    def _orderByCapacityLeft(self, paths):
        """Given a list of arbitrary paths. It ranks them by capacity left (or
        total edges weight).

        Function is implemented in TEControllerLab1
        """
        pass
    

    def toLogDagNames(self, dag):
        """
        """
        dag_to_print = nx.DiGraph()
        
        for (u,v, data) in dag.edges(data=True):
            u_temp = self.db.getNameFromIP(u)
            v_temp = self.db.getNameFromIP(v)
            dag_to_print.add_edge(u_temp, v_temp, **data)
        return dag_to_print
    
    def toLogRouterNames(self, path_list):
        """
        """
        total = []
        if isinstance(path_list[0], list):
            for path in path_list:
                r = [self.db.getNameFromIP(p) for p in path if self.network_graph.is_router(p)] 
                total.append(r)
            return total
        elif isinstance(path_list[0], tuple):
                r = [(self.db.getNameFromIP(u),
                      self.db.getNameFromIP(v)) for (u,v) in path_list
                     if self.network_graph.is_router(u) and self.network_graph.is_router(v)] 
                return r
        else:
            return [self.db.getNameFromIP(p) for p in path_list if self.network_graph.is_router(p)] 

    def toLogFlowNames(self, flow):
        a = "(%s -> %s): %s, t_o: %s, duration: %s" 
        return a%(self.db.getNameFromIP(flow.src.compressed),
                  self.db.getNameFromIP(flow.dst.compressed),
                  flow.setSizeToStr(flow.size),
                  flow.setTimeToStr(flow.start_time),
                  flow.setTimeToStr(flow.duration))  

if __name__ == '__main__':
    log.info("NO-ALGORITHM LOAD BALANCER CONTROLLER\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    lb = LBController()
    lb.run()
