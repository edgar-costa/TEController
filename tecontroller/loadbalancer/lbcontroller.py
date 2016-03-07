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
                
class LBController(DatabaseHandler):
    def __init__(self):
        """It basically reads the network topology from the MyGraphProvider,
        which is running in another thread because
        SouthboundManager.run() is blocking.
        
        Here we are assuming that the topology does not change.
        """
        super(LBController, self).__init__()
        self.flow_allocation = {} # {prefixA: {flow1:path1, flow2:path2},
                                  #  prefixB: {flow1:path3, flow2:path2}}
                                  
        self.eventQueue = eventQueue #From where to read events 
        self.thread_handlers = {} #Used to schedule flow
                                  #alloc. removals
        self.dags = {}
        
        self._stop = threading.Event() #Used to stop the thread
        self.hosts_to_ip = {}
        self.routers_to_ip = {}

        CFG.read(dconf.C1_Cfg) #Must be called before create instance
                               #of SouthboundManager

        # Start the Southbound manager in a different thread    
        self.sbmanager = MyGraphProvider()
        t = threading.Thread(target=self.sbmanager.run, name="Graph Listener")
        t.start()
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Graph Listener thread started\n"%t)

        HAS_INITIAL_GRAPH.wait() #Blocks until initial graph arrives
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Initial graph received\n"%t)

        # Retreieve network from Fibbing Controller
        self.network_graph = self.sbmanager.igp_graph
                 
        # Include BW data inside the initial graph
        n_router_links = self._countRouter2RouterEdges()
        self._readBwDataFromDB()
        i = 0
        while not self._bwInAllRouterEdges(n_router_links):
            i += 1
            self._readBwDataFromDB()            
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Bandwidths written in network_graph after %d iterations\n"%(t,i))

        # Read the initial graph. We keep this as a copy of the
        # physical topology. In initial graph, the instantaneous
        # capacities of the links are kept.
        self.initial_graph = self.network_graph.copy()
        
        # Fill the host2Ip and router2ip attributes
        self._createHost2IPBindings()
        self._createRouter2IPBindings()
        
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Created IP-names bindings\n"%t)
        log.info("\tHostname\tip\tsubnet\n")
        for name, data in self.hosts_to_ip.iteritems():
            log.info("\t%s\t%s\t%s\n"%(name, data['iface_host'], data['iface_router']))
        log.info("\tRouter name\tip\t\n")
        for name, ip in self.routers_to_ip.iteritems():
            log.info("\t%s\t%s\n"%(name, ip))


        # Create here the initial DAGS
        self._createInitialDags()
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Initial DAGS created\n"%t)

        #import ipdb; ipdb.set_trace()#TRACE

        #spawn Json listener thread
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
        
        # Get the flow prefixes
        src_prefix = flow['src'].network.compressed
        dst_prefix = flow['dst'].network.compressed
        
        # Get the current path from source to destination
        currentPaths = self.getActivePaths(src_prefix, dst_prefix)

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


    ## Functions (private) that populate the data structures of the load balancer ###################
    
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
                if self.sbmanager.igp_graph.is_router(x) and self.sbmanager.igp_graph.is_router(y):
                    # Fill edges between routers!
                    bw = self.db.interface_bandwidth(xname, yname)
                    data['bw'] = int(bw*1e6)
                    data['capacity'] = int(bw*1e6)
            else:
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - _readBwDataFromDB(): ERROR: did not find xname and yname"%t)

                
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

    def _createHost2IPBindings(self):
        """Fills the dictionary self.hosts_to_ip with the corresponding
        name-ip pairs
        """
        # Collect hosts only
        hosts = [(name, data) for (name, data) in self.db.network.iteritems() if data['type'] == 'host']
        for (name, data) in hosts:
            node_ip = [v['ip'] for (k, v) in data.iteritems() if isinstance(v, dict)][0]
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

    #########################################################################################################


    ## Useful functions to query network nodes IP, hostnames, connected nodes, etc. #########################
                
    def getSubnetFromHostName(self, hostname):
        """Given a hostname, it returns the subnet in which this hostname
        resides
        """
        subnets = [data['iface_router'] for name, data in
                   self.hosts_to_ip.iteritems() if name == hostname]

        if len(subnets) == 1:
            return subnets[0]
        else:
            return None
        
    def getNodeName(self, ip):
        """Returns the name of the host/or subnet of hosts, given the IP.
        """
        name = [name for name, values in
                self.hosts_to_ip.iteritems() if ip in
                values.values()][0]
        return name
    
    def getEdgeBw(self, x, y):
        """
        Returns the total bandwidth of the network edge between x and y
        """
        return self.initial_graph.get_edge_data(x,y)['bw']
   
    def isRouter(self, x):
        """
        Returns true if x is an ip of a router in the network.
        
        :param x: string representing the IPv4 of a router.
        """
        return x in self.routers_to_ip.values()

    def getEdgeCapacity(self, x, y):
        """Returns the capacity of the network edge between x and y
        """
        return self.initial_graph.get_edge_data(x,y)['capacity']

    #########################################################################################################

    ## Functions related with DAGS ####################################################
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
    
    def getActivePaths(self, src, dst):
        """Both src and dst must be strings representing subnet prefixes
        """
        # Get current active DAG for that destination
        active_dag = self.getActiveDag(dst)
        
        # Get hostnames
        src_hostname = self._db_getNameFromIP(src)
        dst_hostname = self._db_getNameFromIP(dst)

        # Get attached routers
        (src_rname, src_rid) = self._db_getConnectedRouter(src_hostname)
        (dst_rname, dst_rid) = self._db_getConnectedRouter(dst_hostname)

        # Calculate path and return it
        active_paths = self._getAllPathsLimDAG(active_dag, src_rid, dst_rid, 0)
        return active_paths    
    
    def _createInitialDags(self):
        """Populates the self.dags attribute by creating a complete DAG for
        each destination.
        """
    
        apdp = nx.all_pairs_dijkstra_path(self.initial_graph, weight='metric')

        for hostname, values in self.hosts_to_ip.iteritems():
            dag = nx.DiGraph()
            # Get IP of the connected router
            cr = values['router_id']

            # Get subnet prefix
            subnet_prefix = values['iface_router']
            
            other_routers = [rip for rn, rip in self.routers_to_ip.iteritems() if rn != cr]
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
                    t = time.strftime("%H:%M:%S", time.gmtime())
                    to_print = "%s - _createInitialDags(): ECMP is ACTIVE between %s and %s (%s)\n"
                    log.info(to_print%(t, self._db_getNameFromIP(r), self._db_getNameFromIP(subnet_prefix), subnet_prefix))  
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
                        if self.isRouter(u) and self.isRouter(v):
                            dag.add_edge(u,v)
                            edge_data = dag.get_edge_data(u,v)
                            edge_data['active'] = True
                            edge_data['fibbed'] = False
                            edge_data['ongoing_flows'] = False

            # Add DAG to prefix
            self.dags[subnet_prefix] = dag

            
    ######################################################################################
    
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
        return (self.getLiesFromPrefix(dst_prefix) != None)

    
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
        to_print = "%s - addAllocationEntry(): "
        to_print += "flow ALLOCATED to Paths\n"
        log.info(to_print%t)
        log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(prefix))
        log.info("\t* Paths (%s): %s\n"%(len(path_list), str([self.toLogRouterNames(path) for path in path_list])))
        log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))
                        
        # Check first how many ECMP paths are there
        ecmp_paths = float(len(path_list))

        # Current dag for destination
        current_dag = self.getCurrentDag(prefix)
        
        # Iterate the paths
        for path in path_list:
            # Calculate paths with only routers
            path_only_routers = [p for p in path if self.isRouter(p)]

            # Extract the edges of the path
            edges = zip(path_only_routers[:-1], path_only_routers[1:])
            
            # Modify first the current destination dag: ongoing_flows = True
            current_dag = self.switchDagEdgesData(current_dag, edges, ongoing_flows=True)
                        
            for (u, v) in edges:
                # Get capacity of the edge (u,v)
                data = self.initial_graph.get_edge_data(u, v)
                capacity = data.get('capacity', None)
                if capacity:
                    # Substract portion of flow size
                    data['capacity'] -= (flow.size/float(ecmp_paths))

                    # Modify also the capacity data of the reverse edge
                    data_i = self.initial_graph.get_edge_data(v, u)
                    data_i['capacity'] = data['capacity']

                else:
                    to_print = "ERROR: capacity key not found in edge (%s, %s)\n"
                    log.info(to_print%(u, v))

        # Set the current dag
        self.setCurrentDag(prefix, current_dag)
        
        # Define the removeAllocatoinEntry thread
        t = threading.Thread(target=self.removeAllocationEntry, args=(prefix, flow, path_list))
        # Start the thread
        t.start()
        # Add handler to list and start thread
        self.thread_handlers[flow] = t

        
    def removeAllocationEntry(self, prefix, flow, path_list):        
        """
        Removes the flow from the allocation entry prefix and restores the corresponding.
        """
        # Wait until flow finishes
        time.sleep(flow['duration']) 

        if not isinstance(path_list, list):
            raise TypeError("path_list should be a list")
        
        log.info(lineend)
        
        if prefix not in self.flow_allocation.keys():
            # prefix not in table
            raise KeyError("The is no such prefix allocated: %s"%str(prefix))
        else:
            if flow in self.flow_allocation[prefix].keys():
                self.flow_allocation[prefix].pop(flow, None)
            else:
                raise KeyError("%s is not alloacated in this prefix %s"%str(repr(flow)))

        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - removeAllocationEntry(): Flow REMOVED from Paths\n"%t)
        log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(prefix))
        log.info("\t* Paths (%s): %s\n"%(len(path_list), str([self.toLogRouterNames(path) for path in path_list])))
        log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))

        # Check first how many ECMP paths are there
        ecmp_paths = float(len(path_list))

        # Current dag for destination
        current_dag = self.getCurrentDag(prefix)

        # Get current remaining allocated flows for destination
        remaining_flows = self.getAllocatedFlows(prefix)

        # Acumulate edges for which there are flows ongoing
        ongoing_edge_list = []
        for (f, f_path_list) in remaining_flows:
            ongoing_edge_list += self.getEdgesFromPathList(f_path_list)
        
        # Iterate the path_list
        for path in path_list:
            # Get paths with only routers
            path_only_routers = [p for p in path if self.isRouter(p)]

            # Calculate edges of the path
            edges = zip(path_only_routers[:-1], path_only_routers[1:])

            # Calculate which of these edges can be set to ongoing_flows = False
            edges_without_flows = [(u,v) for (u,v) in edges if (u,v) not in ongoing_edge_list]

            # Set them
            current_dag = self.switchDagEdgesData(current_dag, edges_without_flows, ongoing_flows=False)

            # Now add back capacities to edges
            for (u, v) in edges:
                data = self.initial_graph.get_edge_data(u, v)
                capacity = data.get('capacity', None)
                if capacity:
                    data['capacity'] += (flow.size/float(ecmp_paths))
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
        
    def getDefaultDijkstraPathLength(self, network_graph, flow):
        """Returns the length of the default Dijkstra path between the
        flow.src and flow.dst nodes in network_graph.
        """        
        # We assume here that Flow is well formed, and that the
        # interface addresses of the hosts are given.
        src_name = self._db_getNameFromIP(flow['src'].compressed)
        src_router_name, src_router_id = self._db_getConnectedRouter(src_name)
        dst_network = flow['dst'].network.compressed

        # We take only routers in the route
        try:
            default_length = nx.dijkstra_path_length(network_graph, src_router_id, dst_network, weight='metric')
        except nx.NetworkXNoPath:
            t = time.strftime("%H:%M:%S", time.gmtime())
            to_print = "%s - getDefaultDijkstraPathLength(): ERROR: "
            to_print += "No path exists between flow.src and flow.dst\n"
            log.info(to_print%t)
            log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))
            raise nx.NetworkXNoPath
        else:
            return default_length


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

        
    def removePrefixLies(self, prefix, path_list):
        """Remove lies for a given prefix only if there are no more flows
        allocated for that prefix flowing through some edge of
        path_list.

        :param prefix: subnet prefix

        :param path_list: List of paths from source to
                          destination. E.g: [[A,B,C],[A,D,C]]
        """

        log.info("******************************\n")
        # Get the current DAG for that prefix
        current_dag = self.getCurrentDag(prefix)

        #Log it
        #dtp = self.toLogDagNames(current_dag)
        #t = time.strftime("%H:%M:%S", time.gmtime())
        #log.info("\n%s - removePrefixLies(): Initial DAG\n"%t)
        #log.info("%s\n\n"%str(dtp.edges(data=True)))

        # Check if fibbed edge in paths
        thereIsFibbedPath = False
        for path in path_list:
            thereIsFibbedPath = thereIsFibbedPath or self.isFibbedPath(prefix, path)

        if not thereIsFibbedPath:
            # Paths for this flow are not fibbed
            t = time.strftime("%H:%M:%S", time.gmtime())
            to_print = "%s - removePrefixLies(): no fibbed edges found in paths %s for prefix: %s\n"
            log.info(to_print%(t, str(self.toLogRouters(path_list)), self._db_getNameFromIP(prefix)))

        else:
            # Get the lies for prefix
            lsa = self.getLiesFromPrefix(prefix)

            log.info("Found fibbed edges in paths: %s\n"%str(self.toLogRouters(path_list)))

            # Fibbed prefix
            # Let's check if there are other flows for prefix fist
            allocated_flows = self.getAllocatedFlows(prefix)

            # Check if there are flows to prefix going through some
            # path in path_list. If not, we can delete the
            # lies. Otherwise, we must wait.
            if allocated_flows == []:
                log.info("No allocated flows remain for prefix\n")
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
                self.setCurrentDag(current_dag)
                
                # Get the active Dag
                activeDag = self.getActiveDag(prefix)

                # Force it to fibbing
                self.sbmanager.add_dag_requirement(prefix, activeDag.copy())

                # Log it
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - removePrefixLies(): removed lies for prefix: %s\n"%(t, self._db_getNameFromIP(prefix)))
                log.info("\t* LSAs: %s\n"%(str(lsa)))
                
            else:
                log.info("Some flows for prefix still remain\n")
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
                    t = time.strftime("%H:%M:%S", time.gmtime())
                    to_print = "%s - removePrefixLies(): "
                    to_print += "lies for prefix %s not removed. Flows yet ongoing:\n"
                    log.info(to_print%(t, self._db_getNameFromIP(prefix)))
                    for f in flows:
                        log.info("\t%s\n"%(self.toLogFlowNames(f)))
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

                    self.setCurrentDag(current_dag)
                
                    # Get the active Dag
                    activeDag = self.getActiveDag(prefix)

                    # Force it to fibbing
                    self.sbmanager.add_dag_requirement(prefix, activeDag.copy())
                
                    # Log it
                    t = time.strftime("%H:%M:%S", time.gmtime())
                    to_print = "%s - removePrefixLies(): removed lies for prefix: %s\n"
                    log.info(to_print%(t, self._db_getNameFromIP(prefix)))
                    log.info("\tLSAs: %s\n"%(str(lsa)))

        log.info("******************************\n")
        # Log it
        #dtp = self.toLogDagNames(current_dag)
        #t = time.strftime("%H:%M:%S", time.gmtime())
        #log.info("\n%s - removePrefixLies(): Final DAG\n"%t)
        #log.info("%s\n\n"%str(dtp.edges(data=True)))

            
    def getAllocatedFlows(self, prefix):
        """
        Given a prefix, returns a list of tuples:
        [(flow, path), (flow, path), ...]
        """
        if prefix in self.flow_allocation.keys():
            return [(f, p) for f, p in self.flow_allocation[prefix].iteritems()]
        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            to_print = "%s - getAllocatedFlows(): "
            to_print += "prefix %s not yet in flow_allocation table\n"
            log.info(to_print%(t, self._db_getNameFromIP(prefix)))
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
        while lsa_set != set():
            lsa = lsa_set.pop()
            dst = lsa.dest
            if prefix == dst:
                return lsa
        return None

    def getFullEdges(self, network_graph, min_size):
        """
        Returns a list of edges that can't allocate min_size bytes of bandwidth.

        :param network_graph: IGPGraph

        :param min_size: minimum bandwidth size in bytes

        Returns: list of edges. E.g: [(A,B),(B,T),...]
        """
        full_edges = [(u,v) for (u,v,data) in
                 network_graph.edges(data=True) if 'capacity' in
                 data.keys() and data['capacity'] < min_size]

        return full_edges
        
    def getNetworkWithoutEdge(self, network_graph, x, y):
        """Returns a nx.DiGraph representing the network graph without the
        (x,y) edge. x and y must be nodes of network_graph.

        """
        ng_temp = copy.deepcopy(network_graph)
        ng_temp.remove_edge(x, y)
        return ng_temp

    def getNetworkWithoutFullEdges(self, network_graph, flow_size):
        """Returns a nx.DiGraph representing the network graph without the
        edge that can't allocate a flow of flow_size.
        
        :param flow_size: Attribute of a flow defining its size (in bytes).
        """
        ng_temp = network_graph.copy()
        #full_edges = [ng_temp.remove_edge(x,y) for (x, y, data) in
        #              network_graph.edges(data=True) if
        #              data.get('capacity') and data.get('capacity') <=
        #              flow_size and self.isRouter(x) and self.isRouter(y)]
        removed = []
        for (x, y, data) in network_graph.edges(data=True):
            cap = data.get('capacity')
            if cap and cap <= flow_size and self.isRouter(x) and self.isRouter(y):
                edge = (x, y)
                edge_s = (self._db_getNameFromIP(x), self._db_getNameFromIP(y))
                removed.append((edge_s, cap))
                ng_temp.remove_edge(x, y)

        #t = time.strftime("%H:%M:%S", time.gmtime())
        #to_print = "%s - getNetworkWithoutFullEdges(): "
        #to_print += "The following edges can't allocate flow of size: %d\n"
        #log.info(to_print%(t, flow_size))
        #for (edge,cap) in removed:
        #    log.info("\tEdge: %s, capacity: %d\n"%(edge, cap))
        return ng_temp

    
    def getAllPathsRanked(self, igp_graph, start, end):
        """Recursive function that returns an ordered list representing all
        paths between node x and y in network_graph. Paths are ordered
        in increasing length.
        
        :param igp_graph: IGPGraph representing the network
        
        :param start: router if of source's connected router

        :param end: compressed subnet address of the destination
                    prefix."""
        paths = self._getAllPathsLim(igp_graph, start, end, 0)
        ordered_paths = self._orderByLength(paths)
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



    def _getAllPathsLimDAG(self, igp_graph, start, end, k, path=[]):
        """Recursive function that finds all paths from start node to end
        node with maximum length of k.
        """
        # Accumulate nodes in path
        path = path + [start]
        
        if start == end:
            # Arrived to the end. Go back returning everything
            return [path]
            
            
        if not start in igp_graph:
            return []

        paths = []
        for node in igp_graph[start]:
            if node not in path: # Ommiting loops here
                if k == 0:
                    # If we do not want any length limit
                    newpaths = self._getAllPathsLimDAG(igp_graph, node, end, k, path=path)
                    for newpath in newpaths:
                        paths.append(newpath)
                elif len(path) < k+1:
                    newpaths = self._getAllPathsLimDAG(igp_graph, node, end, k, path=path)
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


    def toLogDagNames(self, dag):
        """
        """
        dag_to_print = nx.DiGraph()
        
        for (u,v, data) in dag.edges(data=True):
            u_temp = self._db_getNameFromIP(u)
            v_temp = self._db_getNameFromIP(v)
            dag_to_print.add_edge(u_temp, v_temp, **data)
        return dag_to_print
    
    
    def toLogRouterNames(self, path_list):
        """
        """
        total = []
        if isinstance(path_list[0], list):
            for path in path_list:
                r = [self._db_getNameFromIP(p) for p in path if self.isRouter(p)] 
                total.append(r)
            return total
        elif isinstance(path_list[0], tuple):
                r = [(self._db_getNameFromIP(u),
                      self._db_getNameFromIP(v)) for (u,v) in path_list
                     if self.isRouter(u) and self.isRouter(v)] 
                return r
        else:
            return [self._db_getNameFromIP(p) for p in path_list if self.isRouter(p)] 


    def toLogFlowNames(self, flow):
        a = "(%s -> %s): %s, t_o: %s, duration: %s" 
        return a%(self._db_getNameFromIP(flow.src.compressed),
                  self._db_getNameFromIP(flow.dst.compressed),
                  flow.setSizeToStr(flow.size),
                  flow.setTimeToStr(flow.start_time),
                  flow.setTimeToStr(flow.duration))
    

    

if __name__ == '__main__':
    log.info("NO-ALGORITHM LOAD BALANCER CONTROLLER\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    lb = LBController()
    lb.run()
