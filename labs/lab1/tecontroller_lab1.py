#!/usr/bin/python
from tecontroller.loadbalancer.simplepathlb import SimplePathLB
from tecontroller.linkmonitor.linksmonitor_thread import LinksMonitorThread
from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res import defaultconf as dconf
from tecontroller.res.problib import *
import threading
import time
import Queue

log = get_logger()
lineend = "-"*100+'\n'

class TEControllerLab1(SimplePathLB):
    def __init__(self):
        # Call init method from LBController
        super(TEControllerLab1, self).__init__()

        # Create lock for synchronization on accessing self.cg
        self.capacityGraphLock = threading.Lock()

        # Graph that will hold the link available capacities
        with self.capacityGraphLock:
            self.cg = self._createCapacitiesGraph()

        # Start the links monitorer thread linked to the event queue
        lmt = LinksMonitorThread(capacity_graph = self.cg,
                                 lock = self.capacityGraphLock,
                                 logfile = dconf.LinksMonitor_LogFile,
                                 median_filter=False)
        lmt.start()
        
    def run(self):
        """Main loop that deals with new incoming events
        """
        while not self.isStopped():
            # Get event from the queue (blocking)
            event = self.eventQueue.get()
                        
            if event['type'] == 'newFlowStarted':
                # Log it
                log.info(lineend)
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - run(): %s retrieved from eventQueue\n"%(t, event['type']))
                flow = event['data']
                log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))
                
                # Deal with new flow
                self.dealWithNewFlow(flow)
                
            else:
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - run(): UNKNOWN Event\n"%t)
                log.info("\t* Event: "%str(event))

    def dealWithNewFlow(self, flow):
        """
        Re-writes the parent class method.
        """

        # We acquire the lock now, and assume that capacities are
        # fixed for all execution of the dealWithNewFlow function

        with self.capacityGraphLock:
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
                
            # ECMP active?
            if len(currentPaths) > 1:
                # ECMP is happening
                ecmp_active = True
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - dealWithNewFlow(): ECMP is ACTIVE\n"%t)
            elif len(currentPaths) == 1:
                # ECMP not active
                ecmp_active = False
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - dealWithNewFlow(): ECMP is NOT active\n"%t)
            else:
                t = time.strftime("%H:%M:%S", time.gmtime())
                to_log = "%s - dealWithNewFlow(): ERROR. No path between src and dst\n"
                log.info(to_log%t)
                return

            if ecmp_active:
                # Calculate congestion probability
                
                # Get active dag for current destination
                adag = self.getActiveDag(dst_prefix)
            
                # Insert current available capacities in dag
                for (u, v, data) in adag.edges(data=True):
                    cap = self.cg[u][v]['capacity']
                    data['capacity'] = cap
            
                # Get ingress and egress router
                ingress_router = currentPaths[0][0]
                egress_router = currentPaths[0][-1]

                # compute congestion probability
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - Computing flow congestion probability\n"%t)
                #log.info("\t * DAG: %s\n"%(self.toLogDagNames(adag).edges(data=True)))
                #log.info("\t * Ingress router: %s\n"%ingress_router)
                #log.info("\t * Engress router: %s\n"%egress_router)
                log.info("\t* Flow size: %d\n"%flow.size)
                log.info("\t* EQ Paths: %s\n"%self.toLogRouterNames(currentPaths))
                    
                congProb = flowCongestionProbability(adag, ingress_router,
                                                     egress_router, flow.size)
                # Apply decision function
                # Act accordingly
                # Log it
                to_print = "\t* Flow will be allocated "
                to_print += "with a congestion probability of %.2f\n"
                log.info(to_print%congProb)
                to_print = "\t* Paths: %s\n"
                log.info(to_print%str([self.toLogRouterNames(path) for path in currentPaths]))

                if self.shouldDeactivateECMP(adag, currentPaths, congProb):
                    # Here we have to think what to do when probability of
                    # congestion is too high.
                    pass

                else:
                    # Allocate flow to current paths
                    self.addAllocationEntry(dst_prefix, flow, currentPaths)
            else:
                # currentPath is still a list of a single list: [[A,B,C]]
                # but makes it more understandable
                currentPath = currentPaths

                # Can currentPath allocate flow w/o congestion?
                if self.canAllocateFlow(flow, currentPath):
                    # No congestion. Do nothing
                    t = time.strftime("%H:%M:%S", time.gmtime())
                    log.info("%s - Flow can be ALLOCATED\n"%t)

                    # We just allocate the flow to the currentPath
                    self.addAllocationEntry(dst_prefix, flow, currentPath)

                else:
                    # Congestion created. 
                    t = time.strftime("%H:%M:%S", time.gmtime())
                    log.info("%s - Flow will cause CONGESTION in current path: %s\n"%(t, self.toLogRouterNames(currentPath)))
                
                    # Call the subclassed method to properly 
                    # allocate flow to a congestion-free path
                    self.flowAllocationAlgorithm(dst_prefix, flow, currentPath)
                
    def getMinCapacity(self, path):
        """
        We overwrite the method so that capacities are now checked from the
        SNMP couters data updated by the link monitor thread.
        """
        caps_in_path = []
        for (u,v) in zip(path[:-1], path[1:]):
            edge_data = self.cg.get_edge_data(u, v)
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

    def _createCapacitiesGraph(self):
        # Get copy of the network graph
        ng_copy = self.network_graph.copy()
        cg = self.network_graph.copy()
        
        for node in ng_copy.nodes_iter():
            if not ng_copy.is_router(node):
                cg.remove_node(node)
                
        for (x, y, edge_data) in cg.edges(data=True):
            edge_data['window'] = []
            edge_data['capacity'] = 0
        return cg

    def shouldDeactivateECMP(self, dag, currentPaths, congProb):
        """This function returns a boolean output that decides wheather we
        should deactivate ECMP.

        TODO
        """
        return False

    def getNetworkWithoutFullEdges(self, network_graph, flow_size):
        """Returns a nx.DiGraph representing the network graph without the
        edge that can't allocate a flow of flow_size.
        
        :param network_graph: IGPGraph representing the network.

        :param flow_size: Attribute of a flow defining its size (in bytes).
        """
        ng_temp = network_graph.copy()
        for (x, y, data) in network_graph.edges(data=True):
            cap = self.cg[x][y].get('capacity', None)
            if cap and cap <= flow_size and self.network_graph.is_router(x) and self.network_graph.is_router(y):
                edge = (x, y)
                ng_temp.remove_edge(x, y) 
        return ng_temp

    def getIngressRouter(self, flow):
        """
        """
        src_iface = flow['src']
        for r in self.network_graph.routers:
            if self.network_graph.has_successor(r, src_iface.network.compressed):
                return r
        return None

    def getEgressRouter(self, flow):
        dst_iface = flow['dst']
        for r in self.network_graph.routers:
            if self.network_graph.has_successor(r, dst_iface.network.compressed):
                return r
        return None

    def _orderByCapacityLeft(self, paths):
        """Given a list of arbitrary paths. It ranks them by capacity left (or
        total edges weight).
        
        Function is implemented in TEControllerLab1
        """
        ordered_paths = []
        for path in paths:
            min_capacity = self.getMinCapacity(path)
            ordered_paths.append((path, min_capacity))

        # Now rank them from more to less capacity available
        ordered_paths = sorted(ordered_paths, key=lambda x: x[1], reverse=True)
        return ordered_paths
    
    def flowAllocationAlgorithm(self, dst_prefix, flow, initial_paths):
        """
        """
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Greedy path allocation algorithm started\n"%t)
        start_time = time.time()

        # Get source connected router (src_cr)
        src_iface = flow['src']
        src_prefix = src_iface.network.compressed
        src_cr = [r for r in self.network_graph.routers if
                  self.network_graph.has_successor(r, src_prefix)][0]

        # Get destination network prefix
        dst_iface = flow['dst']
        dst_prefix = dst_iface.network.compressed

        # Get current DAG for destination prefix
        dag = self.getActiveDag(dst_prefix)
        
        # Get required capacity
        required_capacity = flow['size']
        
        # Calculate all possible paths for flow
        all_paths = self.getAllPathsRanked(self.initial_graph, src_cr, dst_prefix, ranked_by='length')

        # Filter only those that are able to allocate flow without congestion
        congestion_free_paths = [path for (path, plen) in all_paths if self.getMinCapacity(path[:-1]) > required_capacity]
                    
        # Get already ongoing flows for that prefix
        ongoing_flow_allocations = self.getAllocatedFlows(dst_prefix)
        
        # Check if congestion free paths exist
        if len(congestion_free_paths) == 0:
            path_found = False
            # No. So allocate it in the least congested path.
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - Flow can't be allocated in the network\n"%t)
            log.info("\t* Allocating it in the path that will create less congestion\n")
            log.info("\t* (But we should look for re-arrangement of already allocated flows...)\n")

            # Here, we should try to re-arrange flows in a way that
            # all of them can be allocated. But for the moment, we
            # will just allocate it in the path that creates less
            # congestion.

            # Get all possible paths from source connected router to
            # destination prefix ranked by capacity left
            all_congested_paths = self.getAllPathsRanked(self.initial_graph, src_cr, dst_prefix, ranked_by='capacity')

            # Set common variable to iterate
            paths_to_iterate = all_congested_paths

            path_congestion_pairs = []
            # Try out all paths, and force the one that will create less congestion.
            # Intermediate results are saved in path_congestion_pairs
            for path in paths_to_iterate:
                # Remove the destination subnet hop node from the path
                path = path[:-1]
                    
                # Initialize accumulated required capacity
                accumulated_required_capacity = required_capacity
                accumulated_congestion = 0
                    
                # Accumulate flows that will be moved
                total_moved_flows = []
                    
                #
                for index, node in enumerate(path[:-1]):
                    # Get flows that will be moved to path
                    moved_flows = [f for (f, pl) in ongoing_flow_allocations for p in pl if node in p]
                        
                    # Accumulate the sizes of the flows that are moved to path
                    accumulated_required_capacity += sum([f.size for f in moved_flows])

                    # Add moved flows to total_moved_flows
                    total_moved_flows += moved_flows
                        
                    # Calculate edge required capacity
                    edge = (node, path[i+1])
                    congestion = accumulated_required_capacity - self.cg[edge[0]][edge[1]]['capacity']

                    # Only add if it's positive, since negative
                    # congestion is not used anyway.
                    if congestion > 0:
                        accumulated_congestion += congestion 

                # Choosing this path, would create such amount of accumulated congestion
                # Append it in variable
                path_congestion_pairs.append((path, accumulated_congestion, total_moved_flows))

            # Let's choose the one with the least congestion
            least_congestion = min(path_congestion_pairs, key=lambda x: x[1])
                
            chosen_path = least_congestion[0]
            chosen_path_congestion = least_congestion[1]
            chosen_path_moved_flows = least_congestion[2]
                
            to_log = "\t* Found path that will create less congestion: %s, congestion %d\n"
            log.info(to_log%(self.toLogRouterNames(chosen_path), chosen_path_congestion))
                        
        else:
            # Yes. There is a path
            path_found = True
            paths_to_iterate = congestion_free_paths

            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - Found path/s that can allocate flow\n"%t)

            path_congestion_pairs = []
            for path in paths_to_iterate:
                # Remove the destination subnet hop node from the path
                path = path[:-1]
                    
                # Initialize accumulated required capacity
                accumulated_required_capacity = required_capacity
                accumulated_congestion = 0
                    
                # Accumulate flows that will be moved
                total_moved_flows = []
                    
                for index, node in enumerate(path[:-1]):
                    # Get flows that will be moved to path
                    moved_flows = [f for (f, pl) in ongoing_flow_allocations for p in pl if node in p]
                        
                    # Accumulate the sizes of the flows that are moved to path
                    accumulated_required_capacity += sum([f.size for f in moved_flows])

                    # Add moved flows to total_moved_flows
                    total_moved_flows += moved_flows
                        
                    # Calculate edge required capacity
                    edge = (node, path[index+1])
                    congestion = accumulated_required_capacity - self.cg[edge[0]][edge[1]]['capacity']

                    if congestion > 0:
                            accumulated_congestion += congestion 

                # Choosing this path, would create such amount of accumulated congestion
                # Append it in variable
                path_congestion_pairs.append((path, accumulated_congestion, total_moved_flows))
                
            # Sort them from less to more congestion created
            path_congestion_pairs_sorted = sorted(path_congestion_pairs, key=lambda x:x[1])

            if path_congestion_pairs_sorted[0][1] != 0:
                log.info("\t* But all of them create congestion when moving other flows\n")
                log.info("\t* Choosing the one that creates less congestion...\n")
                # There is no path that in the end does not create congestion...
                
                # Choose the one with the least congestion
                chosen_path = path_congestion_pairs_sorted[0][0]
                chosen_path_congestion = path_congestion_pairs_sorted[0][1]
                chosen_path_moved_flows = path_congestion_pairs_sorted[0][2]
                log.info("\t* Path (readable): %s\n"%chosen_path)
                log.info("\t* Path (readable): %s\n"%str(self.toLogRouterNames(chosen_path)))
                log.info("\t* Congestion created: %d\n"%chosen_path_congestion)

            else:
                log.info("\t* There are paths that do not create congestion\n")
                #import ipdb; ipdb.set_trace()
                paths_without_congestion = [(p, c, f) for (p, c, f) in path_congestion_pairs if c == 0]
                chosen_path = paths_without_congestion[0][0]
                chosen_path_moved_flows = paths_without_congestion[0][2] 
                log.info("\t* Path (readable): %s\n"%chosen_path)
                log.info("\t* Path (readable): %s\n"%str(self.toLogRouterNames(chosen_path)))

        # From here and below is common code regardless if 
        # congestion_free paths are found or not
        
        # Get edges of new found path
        chosen_path_edges = set(zip(chosen_path[:-1], chosen_path[1:]))
                
        # Deactivate old edges from initial path nodes (won't be
        # used anymore)
        for node in chosen_path:
            # Get active edges of node
            active_edges = self.getActiveEdges(dag, node)
            for a_e in active_edges:
                if a_e not in chosen_path_edges:
                    dag = self.switchDagEdgesData(dag, [(a_e)], active = False)
                    dag = self.switchDagEdgesData(dag, [(a_e)], ongoing_flows = False)
                    
        # Update the flow_allocation
        for f in chosen_path_moved_flows:
            # Get path list of flow
            pl = self.flow_allocation[dst_prefix].get(f)
            
            final_pl = []
            # Iterate previous paths (pp) in path list
            for pp in pl:
                # Check if previous path has a node in common with chosen path
                indexes = [pp.index(node) for node in pp if node in chosen_path]
                if indexes == []:
                    final_pl.append(pp)
                else:
                    index_pp = min(indexes)
                    index_cp = chosen_path.index(pp[index_pp])
                    final_pl.append(pp[:index_pp] + chosen_path[index_cp:])
                
            # Update allocation entry
            self.flow_allocation[dst_prefix][f] = final_pl

        # Add new edges from new computed path
        dag = self.switchDagEdgesData(dag, [chosen_path], active=True)
            
        # This complete DAG goes to the prefix-dag data attribute
        self.setCurrentDag(dst_prefix, dag)
            
        # Retrieve only the active edges to force fibbing
        final_dag = self.getActiveDag(dst_prefix)

        # Log it
        dtp = self.toLogDagNames(final_dag)
        log.info("\t* Final modified dag for prefix: the one with which we fib the prefix\n")
        log.info("\t  %s\n"%str(dtp.edges()))
            
        # Force DAG for dst_prefix
        self.sbmanager.add_dag_requirement(dst_prefix, final_dag)
            
        # Allocate flow to Path. It HAS TO BE DONE after changing the DAG...
        self.addAllocationEntry(dst_prefix, flow, [chosen_path])

        # Log 
        t = time.strftime("%H:%M:%S", time.gmtime())
        to_print = "%s - flowAllocationAlgorithm(): "
        to_print += "Forced forwarding DAG in Southbound Manager\n"
        log.info(to_print%t)
        
if __name__ == '__main__':
    log.info("LOAD BALANCER CONTROLLER - Lab 1 - Enforcing simple paths only\n")
    log.info("-"*70+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    tec = TEControllerLab1()
    tec.run()
                                
