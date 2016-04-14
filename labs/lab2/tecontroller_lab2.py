#!/usr/bin/python
from tecontroller.loadbalancer.simplepathlb import SimplePathLB
from tecontroller.linkmonitor.linksmonitor_thread import LinksMonitorThread
from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res import defaultconf as dconf
from tecontroller.res.problib import ProbabiliyCalculator
import networkx as nx
import threading
import time
import Queue
import itertools as it
import sys
import random
import tecontroller.res.daglib as daglib

log = get_logger()
lineend = "-"*100+'\n'

class TEControllerLab2(SimplePathLB):
    def __init__(self, probabilityAlgorithm=None):
        
        # Call init method from LBController
        super(TEControllerLab2, self).__init__()

        # Instantiate probability calculator object
        self.pc = ProbabiliyCalculator()

        # Create lock for synchronization on accessing self.cg
        self.capacityGraphLock = threading.Lock()

        # Graph that will hold the link available capacities
        with self.capacityGraphLock:
            self.cg = self._createCapacitiesGraph()

        # Variable where we save the last "read-out" copy of the
        # capacity graph
        self.cgc = self.cg.copy()

        # Type of algorithm used to calculate congestion probability
        # in the ECMP part. It can be: simplified, exact or sampled
        self.probabilityAlgorithm = probabilityAlgorithm
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - ECMP Congestion Probability Calculation function used: %s\n"%(t, self.probabilityAlgorithm))
        
        # Start the links monitorer thread linked to the event queue
        lmt = LinksMonitorThread(capacity_graph = self.cg,
                                 lock = self.capacityGraphLock,
                                 logfile = dconf.LinksMonitor_LogFile,
                                 median_filter=False)
        lmt.start()
        
    def run(self):
        """Main loop that deals with new incoming events
        """
        getTimeout = 1

        while not self.isStopped():
            
            try:
                log.info("*** Reading from event queue...\n")
                event = self.eventQueue.get(timeout=getTimeout)
            except:
                log.info("*** Timeout occurred\n")
                event = None
                    
            # Check if flows allocations still pending for feedback
            if self.pendingForFeedback != {}:
                log.info("*** Some flows yet neet feedback...\n")
                if not self.feedbackResponseQueue.empty():
                    # Read element from responseQueue
                    responsePathDict = self.feedbackResponseQueue.get()
                    self.dealWithAllocationFeedback(responsePathDict)
                else:
                    log.info("*** But nothing is on the responseQueue...\n")
                    
            if event and event['type'] == 'newFlowStarted':
                log.info("*** newFlowStarted event received...\n")
                # Log it
                log.info(lineend)
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - run(): %s retrieved from eventQueue\n"%(t, event['type']))
                flow = event['data']
                log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))

                # We force that upon dealing with flow, the self.dags
                # and self.flow_allocation dictionaries are not
                # modified.
                with self.dagsLock:
                    with self.flowAllocationLock:
                        # Deal with new flow
                        self.dealWithNewFlow(flow)
                log.info("*** dealWithNewFlow finished...\n")
                
            elif event:
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - run(): UNKNOWN Event\n"%t)
                log.info("\t* Event: "%str(event))

            if self.pendingForFeedback != {}:
                log.info("*** We still need feedback for some flows...\n")
                log.info("*** Puting pendingForFeedback dictionary into requestQueue...\n")

                # Put into queue
                self.feedbackRequestQueue.put(self.pendingForFeedback.copy())

    def dealWithAllocationFeedback(self, responsePathDict):
        # Acquire locks for self.flow_allocation and self.dags
        # dictionaries
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Allocation feedback received: processing...\n"%t)
        
        self.flowAllocationLock.acquire()
        self.dagsLock.acquire()

        # Iterate flows for which there is allocation feedback
        for (f, p) in responsePathDict.iteritems():
            flow_dst_prefix = self.getCurrentOSPFPrefix(f.dst.compressed)
            flow_dst_prefix = flow_dst_prefix.compressed
            
            # Update flow_allocation dictionary
            if flow_dst_prefix in self.flow_allocation.keys():
                pl = self.flow_allocation[flow_dst_prefix].get(f, None)
                if pl == None:
                    # It means flow finished... so we should remove it
                    # from pendingForFeedback
                    self.pendingForFeedback.pop(f)
                else:
                    # Log a bit
                    to_log = "\t* %s allocated to %s.\n\t  Previous options: %s\n"
                    log.info(to_log%(self.toLogFlowNames(f), self.toLogRouterNames([p]), self.toLogRouterNames(pl)))

                    # Update allocation
                    self.flow_allocation[flow_dst_prefix][f] = [p]

                    # Update current DAG (ongoing_flows = False) should be
                    # done here. But since it's not used anyway, we skip
                    # it for now...
                    
                    # Remove flow from pendingForFeedback
                    if f in self.pendingForFeedback.keys():
                        self.pendingForFeedback.pop(f)
                    else:
                        raise KeyError
            else:
                # It means flow finished... so we should remove it
                # from pendingForFeedback
                self.pendingForFeedback.pop(f)

        # Release locks
        self.flowAllocationLock.release()
        self.dagsLock.release()

    def dealWithNewFlow(self, flow):
        """
        Re-writes the parent class method.
        """
        # We acquire the lock now, and assume that capacities are
        # fixed for all execution of the dealWithNewFlow function
        with self.capacityGraphLock:
            # Make copy of the capacity graph at that moment in time
            # and release the lock.
            self.cgc = self.cg.copy()

        # Log capacities in stdout
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - Copy of the capacity graph done. Current edge usages:\n"%t)
        for (x, y, data) in self.cgc.edges(data=True):
            currentLoad = self.getCurrentEdgeLoad(x,y)
            x_name = self.db.getNameFromIP(x)
            y_name = self.db.getNameFromIP(y)
            log.info("\t(%s, %s) -> Capacity available %d (%.2f%% full)\n"%(x_name, y_name, data['capacity'], currentLoad*100))
            
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
        log.info("\t* Flow matches the following OSPF advertized prefix: %s\n"%str(dst_prefix))                
            
        # Get current Active DAG for prefix
        adag = self.getActiveDag(dst_prefix)
        log.info("\t* Active DAG for %s: %s\n"%(dst_prefix, self.toLogDagNames(adag).edges()))

        # Get the current path from source to destination
        currentPaths = self.getActivePaths(src_iface, dst_iface, dst_prefix)
        log.info("\t* Current paths: %s\n"%str(self.toLogRouterNames(currentPaths)))
            
        # ECMP active?
        if len(currentPaths) > 1:
            # ECMP is happening
            ecmp_active = True
            log.info("\t* ECMP is ACTIVE in some routers in path\n")
            
        elif len(currentPaths) == 1:
            # ECMP not active
            ecmp_active = False
            log.info("\t* ECMP is NOT active\n")
        
        # Error here
        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            to_log = "%s - dealWithNewFlow(): ERROR. No path between src and dst\n"
            log.info(to_log%t)
            return

        # ECMP active in default paths
        if ecmp_active:
            # Calculate congestion probability
            
            # Insert current available capacities in DAG
            for (u, v, data) in adag.edges(data=True):
                cap = self.cgc[u][v]['capacity']
                data['capacity'] = cap
            
            # Get ingress and egress router
            ingress_router = currentPaths[0][0]
            egress_router = currentPaths[0][-1]

            # Compute congestion probability
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - Computing flow congestion probability\n"%t)
            log.info("\t* Flow size: %d\n"%flow.size)
            log.info("\t* Equal Cost Paths: %s\n"%self.toLogRouterNames(currentPaths))
            
            with self.pc.timer as t:
                congProb = self.pc.flowCongestionProbability(adag, ingress_router,
                                                                 egress_router, flow.size)

            # Log it
            to_print = "\t* Flow will be allocated with a congestion probability of %.2f%%\n"
            log.info(to_print%(congProb*100.0))
            log.info("\t* It took %s ms to compute probabilities\n"%str(self.pc.timer.msecs))
            to_print = "\t* Paths: %s\n"
            log.info(to_print%str([self.toLogRouterNames(path) for path in currentPaths]))

            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - Applying decision function...\n"%t)

            # Apply decision function
            if self.shouldDeactivateECMP(adag, currentPaths, congProb):
                # Here we have to think what to do when probability of
                # congestion is too high.
                # Here we have to think what to do when probability of
                # congestion is too high.
                log.info("\t* ECMP SHOULD be de-activated!\n")
                self.flowAllocationAlgorithm(dst_prefix, flow, currentPaths)

            else:
                log.info("\t* ECMP Should NOT de-activated!\n")
                # Allocate flow to current paths
                self.addAllocationEntry(dst_prefix, flow, currentPaths)

        # ECMP is not active in default paths       
        else:
            # currentPath is still a list of a single list: [[A,B,C]]
            # but makes it more understandable
            currentPath = currentPaths

            # Can currentPath allocate flow w/o congestion?
            if self.canAllocateFlow(flow, currentPath):
                # No congestion. Do nothing
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - Flow can be ALLOCATED in current path: %s\n"%(t, self.toLogRouterNames(currentPath)))

                (edge, currentLoad) = self.getFullestEdge(currentPath[0])
                increase = self.utilizationIncrease(currentPath[0], flow)
                log.info("\t* Min capacity edge %s is %.1f%% full\n"%(str(edge), currentLoad*100))
                log.info("\t* New Flow with size %d represents an increase of %.1f%%\n"%(flow.size, increase*100))

                # We just allocate the flow to the currentPath
                self.addAllocationEntry(dst_prefix, flow, currentPath)

            else:
                # Congestion created. 
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - Flow will cause CONGESTION in current path: %s\n"%(t, self.toLogRouterNames(currentPath)))

                (edge, currentLoad) = self.getFullestEdge(currentPath[0])
                increase = self.utilizationIncrease(currentPath[0], flow)
                log.info("\t* Min capacity edge %s is %.1f%% full\n"%(str(edge), currentLoad*100))
                log.info("\t* New Flow with size %d represents an increase of %.1f%%\n"%(flow.size, increase*100))
            
                # Call the subclassed method to properly 
                # allocate flow to a congestion-free path
                self.flowAllocationAlgorithm(dst_prefix, flow, currentPath)

    def shouldDeactivateECMP(self, dag, currentPaths, congProb):
        """This function returns a boolean output that decides wheather we
        should deactivate ECMP.

        TODO
        """
        if congProb > 0.5:
            return True
        else:
            return False

    def canAllocateFlow(self, flow, path_list):
        """Returns true if there is at least flow.size bandwidth available in
        all links along the path (or multiple paths in case of ECMP)
        from flow.src to src.dst,
        """
        for path in path_list:
            # Get edge with minimum capacity of the path
            ((x,y), minCap) = self.getMinCapacityEdge(path)
            bw = self.cgc[x][y].get('bw')

            currentload = (bw - minCap)/float(bw)
            if currentload > self.congestionThreshold:
                return False
            else:
                nextload = ((bw - minCap) + flow.size)/float(bw)
                if nextload > self.congestionThreshold:
                    return False
        return True

    def getFullestEdge(self, path):
        # Get edge with minimum capacity of the path
        ((x,y), minCap) = self.getMinCapacityEdge(path)
        bw = self.cgc[x][y].get('bw')

        currentLoad = (bw - minCap)/float(bw)
        return ((x,y), currentLoad)

    def getCurrentEdgeLoad(self, x,y):
        cap = self.cgc[x][y].get('capacity')
        bw = self.cgc[x][y].get('bw')
        if cap and bw:
            currentLoad = (bw - cap)/float(bw)
        return currentLoad
    
    def getMinCapacityEdge(self, path):
        caps_edges = []
        for (u,v) in zip(path[:-1], path[1:]):
            edge_data = self.cgc.get_edge_data(u, v)
            if edge_data:
                cap = edge_data.get('capacity', None)
                caps_edges.append(((u,v), cap))
        try:
            min_cap_edge = min(caps_edges, key=lambda x: x[1])
            return min_cap_edge
        
        except ValueError:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - getMinCapacity(): ERROR: min could not be calculated\n"%t)
            log.info("Argument should be a list! (not a list of lists)")
            raise ValueError
 
    def getMinCapacity(self, path):
        """
        We overwrite the method so that capacities are now checked from the
        SNMP couters data updated by the link monitor thread.
        """
        caps_in_path = []
        for (u,v) in zip(path[:-1], path[1:]):
            edge_data = self.cgc.get_edge_data(u, v)
            if edge_data:
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

    def utilizationIncrease(self, path, flow):
        # Get edge with minimum capacity of the path
        ((x,y), minCap) = self.getMinCapacityEdge(path)
        bw = self.cgc[x][y].get('bw')

        currentLoad = (bw - minCap)/float(bw)
        nextLoad = ((bw - minCap) + flow.size)/float(bw)
        return nextLoad - currentLoad

    def getIngressRouter(self, flow):
        """
        """
        src_iface = flow['src']
        for r in self.network_graph.routers:
            src_prefix = src_iface.network.compressed
            if self.network_graph.has_successor(r, src_prefix) and self.network_graph[r][src_prefix]['fake'] == False:
                return r
        return None

    def getEgressRouter(self, flow):
        dst_iface = flow['dst']
        for r in self.network_graph.routers:
            dst_prefix = dst_iface.network.compressed
            if self.network_graph.has_successor(r, dst_prefix) and self.network_graph[r][dst_prefix]['fake'] == False:
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
        log.info("%s - Flow Allocation algorithm started\n"%t)
        f_start_time = time.time()

        # Get source connected router (src_cr)
        src_iface = flow['src']
        src_prefix = src_iface.network.compressed
        src_cr = [r for r in self.network_graph.routers if
                  self.network_graph.has_successor(r, src_prefix) and
                  self.network_graph[r][src_prefix]['fake'] == False][0]

        # Get current matching destination prefix
        dst_prefix = dst_prefix

        # Get current active DAG (all-sources dag)
        adag = self.getActiveDag(dst_prefix)

        # Get flow ingress and egress routers
        ingress_rid = self.getIngressRouter(flow)
        egress_rid = self.getEgressRouter(flow)

        if self.shouldCalculateAllDAGs():
            # Check all DAGs
            all_dags = daglib.getAllPossibleDags(self.initial_graph, ingress_rid, egress_rid)
            log.info("\t* All possible DAGs should be considered (single+multiple path DAGs)\n")

        else:
            # Check only Single-Path dags
            all_dags = daglib.getAllPossibleSimplePathDags(self.initial_graph, ingress_rid, egress_rid)
            log.info("\t* Only single path DAGs are considered\n")

        # Choose first which probability calculation algorithm is
        # going to be used
        if not self.probabilityAlgorithm:
            probAlgo = self.chooseProbabilityAlgorithm()
        else:
            probAlgo = self.probabilityAlgorithm
        log.info("\t* Algorithm to compute Pc chosen: %s\n"%probAlgo)
            
        # Randomly shuffle DAGs
        random.shuffle(all_dags)

        ## Repeat n times:
        n_iterations = self.getNIterations(all_dags)
        to_log = "\t* First level sampling: %d samples out of %d\n"
        log.info(to_log%(n_iterations, len(all_dags)))

        results = []
        #foundEarlyDag = False

        start_time = time.time()
        # First level sampling
        for i in range(n_iterations):
            # Try ouf unique random ri-dx DAG
            ri_dx_dag = all_dags[i]
            
            # Compute the new all-routers DAG
            new_adag = self.recomputeAllSourcesDag(adag, ri_dx_dag)

            # Add virtual capacities to new_adag
            new_adag = self.addVirtualCapacities(new_adag, dst_prefix)

            # Compute new path taken by sources in new re-computed DAG
            new_sources = self.computeNewSources(new_adag, flow, dst_prefix)

            # Compute congestion probability Pc
            congProb = self.computeCongProb(probAlgo, new_adag, new_sources)

            # If found congProb low enough
            #if self.isLowEnough(congProb):
                # Chose and break
            #    foundEarlyDag = True
            #    chosen_ridx_dag = ri_dx_dag
            #    chosen_alls_dag = new_adag
            #    chosen_congProb = congProb
            #    break

            #else:
            # Note down results
            results.append((ri_dx_dag, new_adag, congProb, new_sources))

        log.info("\t* It took %.3f ms to find optimal DAG\n"%((time.time()-start_time)*1000.0))

        # Now choose ri-dx DAG that minimizes Pc
        # Sort results by increasing congestion probability
        sorted_results = sorted(results, key=lambda x: x[2])

        # Get minimum congProb obtained
        min_congProb = min(sorted_results, key=lambda x: x[2])

        # Filter those with the same congProb as minimum
        min_results = filter(lambda x: x[2] == min_congProb[2], sorted_results)

        # Check if many with same results
        if len(min_results) > 1:
            # Take the one with the shortest overall distance

            # So far we only choose one at random
            random.shuffle(min_results)

            # Chosen one
            chosen_ridx_dag = min_results[0][0]
            chosen_alls_dag = min_results[0][1]
            chosen_congProb = min_results[0][2]
            chosen_newsources = min_results[0][3]
        else:
            chosen_ridx_dag = min_congProb[0]
            chosen_alls_dag = min_congProb[1]
            chosen_congProb = min_congProb[2]
            chosen_newsources = min_congProb[3]

        log.info("\t* Chosen ri->dx DAG: %s\n"%(str(self.toLogDagNames(chosen_ridx_dag).edges())))
        log.info("\t* Chosen complete DAG: %s\n"%(str(self.toLogDagNames(chosen_alls_dag).edges())))
        log.info("\t* Congestion Probability Pc: %.2f%%\n"%(chosen_congProb*100.0))
            
        # to chose the one that minimizes congProb
        #if not foundEarlyDag:
        #    chosen = min(results, key=lambda x: x[2])
        #    chosen_ridx_dag = chosen[0]
        #    chosen_alls_dag = chosen[1]
        #    chosen_congProb = chosen[2]

        # Modify current all-sources DAG for destination (modify edges
        # accordingly) and set it to variable self.dags[dst_prefix] =
        # cdag.copy()
        log.info("\t* Updating current complete DAG to destination %s\n"%str(dst_prefix))
        self.updateCurrentDag(dst_prefix, chosen_alls_dag)
        
        # Extact active DAG
        new_active_dag = self.getActiveDag(dst_prefix)

        # Update flow allocations with new path taken by flows
        log.info("\t* Updating flow allocations ...\n")
        self.updateFlowAllocations(dst_prefix, chosen_newsources)

        # Spawn removeAllocation for new flow
        # Define the removeAllocatoinEntry thread
        t = threading.Thread(target=self.removeAllocationEntry, args=(dst_prefix, flow))
        # Start the thread
        t.start()
        # Add handler to list and start thread
        self.thread_handlers[flow] = t

        # Fib final DAG
        log.info("\t* Fibbing final chosen complete DAG...\n")
        self.sbmanager.add_dag_requirement(dst_prefix, new_active_dag.copy())

        # Leave
        t = time.strftime("%H:%M:%S", time.gmtime())
        to_log = "%s - Flow Allocation algorithm finished - elapsed time: %.5f s\n"
        log.info(to_log%(t, (time.time()-f_start_time)))


        
    def removeAllocationEntry(self, prefix, flow):
        """
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
        to_log = "\t* Paths (%s): %s\n"
        log.info(to_log%(len(path_list), str(self.toLogRouterNames(path_list))))
        log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))

        # Current dag for destination
        current_dag = self.getCurrentDag(prefix)
        
        # Get the active Dag
        activeDag = self.getActiveDag(prefix)

        # Log active DAG
        to_log = "\t* removeAllocationEntry: current active DAG\n\t  %s\n"
        log.info(to_log%str(self.toLogDagNames(activeDag).edges()))
        
        # Get current remaining allocated flows for destination
        remaining_flows = self.getAllocatedFlows(prefix)

        # Create DAG showing remaining flow paths only
        edges_with_flows = []
        for (f, pl) in remaining_flows:
            edges_with_flows += self.getEdgesFromPathList(f_path_list)        
        edges_with_flows = list(set(edges_with_flows))
        remaining_traffic_dag = nx.DiGraph()
        remaining_traffic_dag.add_nodes_from(activeDag.nodes())
        remaining_traffic_dag.add_edges_from(edges_with_flows)
        
        # Difference with active DAG can be set to 'ongoing_flows' = False
        to_set_noflows = nx.difference(activeDag, remaining_traffic_dag)
        for (x, y) in to_set_noflows.edges_iter():
            current_dag[x][y]['ongoing_flows'] = False
            
        # Set the new calculated dag to its destination prefix dag
        self.setCurrentDag(prefix, current_dag)

        # Check if we can set destination forwarding to the initial
        # default OSPF DAG
        if len(remaining_flows) == 0:
            # Log a bit
            to_log = "\t* No more flows remain to prefix."
            to_log += " Re-setting to initial OSPF DAG\n"
            log.info(to_log)
            
            # Set forwarding to original
            self.setOSPFOriginalDAG(prefix)
        else:
            # Log it only
            log.info("\t* Some flows to prefix still remain.\n")

            # Log final DAG that is foced
            activeDag = self.getActiveDag(prefix)
            to_log = "\t* removePrefixLies: final active DAG\n\t  %s\n"
            log.info(to_log%str(self.toLogDagNames(activeDag).edges()))

            # Force it to fibbing
            self.sbmanager.add_dag_requirement(prefix, activeDag.copy())
            log.info(lineend)
        
        # Release locks
        self.flowAllocationLock.release()
        self.dagsLock.release()

    def setOSPFOriginalDAG(self, prefix):
        """
        """
        # Iterate current DAG
        cdag = self.getCurrentDag(prefix)
        
        # Retrieve those edges with default=True. Set them to active
        # and set the rest to inactive
        for (x, y) in cdag.edges_iter():
            if cdag[x][y].get('default', False) == True:
                cdag[x][y]['active'] = True
            else:
                cdag[x][y]['active'] = False

        # Set modified current dag
        self.setCurrentDag(prefix, cdag)
        
        # Retrieve active dag
        activeDag = self.getActiveDag(prefix)
        to_log = "\t* removePrefixLies: final active DAG\n\t  %s\n"
        log.info(to_log%str(self.toLogDagNames(activeDag).edges()))
        
        # Force it to fibbing
        self.sbmanager.add_dag_requirement(prefix, activeDag.copy())
        
        log.info(lineend)
        
    def updateFlowAllocations(self, dst_prefix, new_sources):
        """
        Updates allocations of flows given by the new forced DAG
        """
        # New dict
        new_dict = {}
        
        # Update with new allocations
        for (f, pl) in new_sources:
            # Accumulate it in new dict
            new_dict[f] = pl

            # Path list before
            pl_before = self.flow_allocation[dst_prefix].get(f)

            # Log a bit
            if pl_before:
                to_log = "\t%s before: %s, now allocated to: %s\n"
                log.info(to_log%(self.toLogFlowNames(f), self.toLogRouterNames(pl_before), self.toLogRouterNames(pl)))
            else:
                to_log = "\t%s allocated to: %s\n"
                log.info(to_log%(self.toLogFlowNames(f), self.toLogRouterNames(pl)))
                
            # Check if flow needs feedback
            if len(pl) > 1:
                log.info("\t* Adding %s to allocation feedback...\n"%self.toLogFlowNames(f))
                self.pendingForFeedback[f] = pl
                
        # Re-set flow allocations for that prefix
        self.flow_allocation[dst_prefix] = new_dict



    def updateCurrentDag(self, dst_prefix, new_activeDag):
        """
        :param dst_prefix:
        :param new_activeDag: DAG directing any possible router towards dst_prefix
        """
        # Get current complete DAG
        c_completeDag = self.getCurrentDag(dst_prefix)
        
        # Get current active DAG
        c_activeDag = self.getActiveDag(dst_prefix)

        # Get edges to set 'active' = False in c_completeDag
        edges_to_inactive = nx.difference(c_activeDag, new_activeDag)
        # Set them
        for (x, y) in edges_to_inactive.edges_iter():
            if not c_completeDag.has_edge(x, y):
                c_completeDag.add_edge(x, y)
                c_completeDag[x][y]['default'] = False
            c_completeDag[x][y]['active'] = False
            c_completeDag[x][y]['ongoing_flows'] = False
            
        # Get edges to set 'active' = True in c_completeDag
        edges_to_active = nx.difference(new_activeDag, c_activeDag)
        # Set them
        for (x, y) in edges_to_active.edges_iter():
            if not c_completeDag.has_edge(x, y):
                c_completeDag.add_edge(x, y)
                c_completeDag[x][y]['default'] = False
            c_completeDag[x][y]['active'] = True
            c_completeDag[x][y]['ongoing_flows'] = True

        # Set new computed curren complete DAG to dict attribute
        self.setCurrentDag(dst_prefix, c_completeDag)
        
    def recomputeAllSourcesDag(self, all_dag, new_ridx_dag):
        """
        Given the initial all_routers_dag, and the new chosen ridxDag, we compute
        the newly created all_routers_dag merging the previous one while forcing the
        new ridxDag.
        """
        # Add 'flag' in new ridx dag
        edges = new_ridx_dag.edges()
        ridx_dag = nx.DiGraph()
        ridx_dag.add_edges_from(edges, flag=True)
        
        # Compose it with all_dag
        new_adag = nx.compose(all_dag, ridx_dag)

        # Iterate new ridx nodes. Remove those outgoing edges from the same node 
        # in all_dag that do not have 'flag'.
        final_all_dag = new_adag.copy()

        # Get edges to remove
        edges_to_remove = [(x, y) for node in new_ridx_dag.nodes() for
                           (x, y, data) in new_adag.edges(data=True)
                           if node == x and not data.get('flag')]

        # Remove them
        final_all_dag.remove_edges_from(edges_to_remove)
        
        # Return modified all_dag
        return final_all_dag

    def addVirtualCapacities(self, all_dag, dst_prefix):
        """
        Adds the virtual capacities to all sources dag. Virtual capacities 
        are those computed by: taking current capacities, and substracting
        the flow sizes for dst_prefix traffic in the corresponding paths.

        We assume here that all allocations for flows to dst_prefix are known.
        """
        # Get ongoing flows
        sources = self.getAllocatedFlows(dst_prefix)

        # Extract the single only path
        sources = [(f, p[0]) for (f, p) in sources if len(p) == 1]

        # Iterate each edge on all_dag
        for (x, y, data) in all_dag.edges(data=True):
            # Get edge capacity
            cap = self.cgc[x][y].get('capacity')

            # Accumulate sizes of flows that pass through there
            to_add = sum([f.size for (f, p) in sources if (x, y) in zip(p[:-1], p[1:])])
            
            # Compute new virtual capacity
            vcap = cap + to_add

            # Update new size in all_dag edge
            data['capacity'] = vcap

            # Remove flag
            if 'flag' in data.keys():
                data.pop('flag')

        return all_dag    

    # TODO FUNCTIONS #########################################

    def getNIterations(self, all_dags):
        # We iterate all of them now

        return len(all_dags)

    def shouldCalculateAllDAGs(self):

        return True

    def isLowEnough(self, congProb):
        if congProb < 0.1:
            return True
        else:
            return False

    def chooseProbabilityAlgorithm(self):
        # This should be replaced by the results of the evaluation
        return 'exact'

    def computeNewSources(self, new_adag, flow, dst_prefix):
        """
        Returns the list of tuples that assigns each flow to
        dst_prefix to its new computed on the new all-sources dag.
        """
        # Fetch allocated flows
        ongoing_flows = self.getAllocatedFlows(dst_prefix)
        flows = [flow]+[f for (f, p) in ongoing_flows]

        # Calculate ingress routers for each flow
        irs = map(lambda x: self.getIngressRouter(x), flows)

        # Calculate egress router (should be the same for all)
        er = self.getEgressRouter(flow)

        # Result list of tuples (flow, [p1, p2])
        sources_to_paths = []

        # Search for all paths for each flow
        for index, f in enumerate(flows):
            all_flow_paths = daglib.getAllPathsLim(new_adag, irs[index], er, 0)
            sources_to_paths.append((f, all_flow_paths))

        return sources_to_paths

    def computeCongProb(self, algorithm, all_dag, sources):
        """
        :param algorithm: name of the algorithm to compute the probability with.
        :param all_dag: all routers dag with virtual capacities
        :param sources: list of tuples (f, pl) with flows and corresponding allocated
                        possible paths
        """
        # Convert flows into sizes and paths into capacities
        flow_sizes = [f.size for (f, pl) in sources]
        flow_paths = [pl for (f, pl) in sources]

        if algorithm == 'exact':
            congProb = self.pc.ExactCongestionProbability(all_dag, flow_paths, flow_sizes)
        elif algorithm == 'sampled':
            pass
        else:
            pass
        return congProb

    ##########################################################
        
    def _getVirtualMinCapacity(self, capacity_graph, path):
        caps = []
        for (u, v) in zip(path[:-1], path[1:]):
            caps.append(capacity_graph[u][v].get('capacity', None))
        return min(caps)
     
    def SimplifiedProbability(self, all_path_subsets, flow_sizes):
        # Get biggest flow size
        max_flow_size = max(flow_sizes)

        # Compute how many flows there are. We assume here we all have
        # max_flow_size
        n = len(flow_sizes)

        # Iterate path combinations and choose the one that minimizes
        # congestion probability
        with self.pc.timer as t:
            probs_items = []
            for path_subset in all_path_subsets:
                # Calculate minimun path capacity and parameter m
                minimum_path_capacity = min([pvcap for (path, pvcap) in path_subset])
                m = len(path_subset)
                
                # Calculate k: how many flows can each path allocate at max.
                k = int(minimum_path_capacity/max_flow_size)

                # Compute congestion probability
                congProb = self.pc.SCongestionProbability(m, n, k)

                log.info("\tPaths: %s\n"%(str(self.toLogRouterNames([p for p,c in path_subset]))))
                log.info("\tMinimun path capacity: %s\n"%(str(minimum_path_capacity)))
                log.info("\tMax flow size: %s\n"%(str(max_flow_size)))
                log.info("\tm: %d, n: %d, k: %d -> congProb: %.2f\n"%(m,n,k,congProb))
                
                # Append intermediate result
                probs_items.append((path_subset, congProb))

        # Get path subset that minimizes congestion probability
        chosen_subset = min(probs_items, key=lambda x: x[1])

        # Get the paths only
        chosen_paths = [p for (p, c) in chosen_subset[0]]

        # Get the congestion probability
        congProb_chosen_paths = chosen_subset[1]

        # Log search results
        to_log = "\t* ECMP on paths: %s minimizes the congestion probability: %.2f%%\n"
        log.info(to_log%(str(self.toLogRouterNames(chosen_paths)), congProb_chosen_paths*100))
        to_log = "\t* It took %s ms to calculate probabilities\n"
        log.info(to_log%(str(self.pc.timer.msecs)))

        return chosen_paths

    def ExactProbability(self, path_capacities, flow_sizes):
        """
        """
        # Iterate path combinations and choose the one that minimizes
        # congestion probability
        with self.pc.timer as t:
            probs_items = []
            for path_subset in all_path_subsets:
                # Save path capacities only
                m = [pvcap for (path, pvcap) in path_subset]

                # Save flow sizes
                n = flow_sizes

                # Compute congestion probability
                congProb = self.pc.ExactCongestionProbability(m, n)

                # Log results
                paths = [p for p,c in path_subset]
                log.info("\tPath combination:\n")
                for i, p in enumerate(paths):
                    log.info("\t\t* %s, capacity: %s\n"%(str(self.toLogRouterNames(p)), m[i]))
                log.info("\tExact congestion probability: %.2f\n\n"%(congProb))
                
                # Append intermediate result
                probs_items.append((path_subset, congProb))

        # Get path subset that minimizes congestion probability
        chosen_subset = min(probs_items, key=lambda x: x[1])

        # Get the paths only
        chosen_paths = [p for (p, c) in chosen_subset[0]]

        # Get the congestion probability
        congProb_chosen_paths = chosen_subset[1]

        # Log search results
        to_log = "\t* ECMP on paths: %s minimizes the congestion probability: %.2f%%\n"
        log.info(to_log%(str(self.toLogRouterNames(chosen_paths)), congProb_chosen_paths*100))
        to_log = "\t* It took %s ms to calculate probabilities\n"
        log.info(to_log%(str(self.pc.timer.msecs)))
        return chosen_paths
    
    def SampledProbability(self, all_path_subsets, flow_sizes):
        # Iterate path combinations and choose the one that minimizes
        # congestion probability
        with self.pc.timer as t:
            probs_items = []
            for path_subset in all_path_subsets:
                # Save path capacities only
                m = [pvcap for (path, pvcap) in path_subset]
                
                # Save flow sizes
                n = flow_sizes

                # Compute congestion probability
                (congProb, std) = self.pc.SampledCongestionProbability(m, n, percentage=30, estimate=10)

                # Log results
                paths = [p for p,c in path_subset]
                log.info("\tPath combination:\n")
                for i, p in enumerate(paths):
                    log.info("\t\t* %s, capacity: %s\n"%(str(self.toLogRouterNames(p)), m[i]))
                if not std:
                    log.info("\tExact congestion probability: %.2f\n\n"%(congProb))
                else:
                    log.info("\tExact congestion probability: %.2f +/- %.5f\n\n"%(congProb, std))
                # Append intermediate result
                probs_items.append((path_subset, congProb))

        # Get path subset that minimizes congestion probability
        chosen_subset = min(probs_items, key=lambda x: x[1])

        # Get the paths only
        chosen_paths = [p for (p, c) in chosen_subset[0]]

        # Get the congestion probability
        congProb_chosen_paths = chosen_subset[1]

        # Log search results
        to_log = "\t* ECMP on paths: %s minimizes the congestion probability: %.2f%%\n"
        log.info(to_log%(str(self.toLogRouterNames(chosen_paths)), congProb_chosen_paths*100))
        to_log = "\t* It took %s ms to calculate probabilities\n"
        log.info(to_log%(str(self.pc.timer.msecs)))
        return chosen_paths

if __name__ == '__main__':
    log.info("LOAD BALANCER CONTROLLER - Lab 2 - Enforcing simple paths + ECMP when needed\n")
    log.info("-"*90+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)

    if len(sys.argv) == 2:
        algorithm = sys.argv[1]
    else:
        algorithm = 'exact'
    
    tec = TEControllerLab2(probabilityAlgorithm=algorithm)
    tec.run()
                                
