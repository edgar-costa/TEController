#!/usr/bin/python

from tecontroller.loadbalancer.lbcontroller import LBController
from tecontroller.res import defaultconf as dconf

from fibbingnode.misc.mininetlib import get_logger

import networkx as nx
import threading
import time

log = get_logger()
lineend = "-"*100+'\n'

class SimplePathLB(LBController):
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
        super(SimplePathLB, self).__init__(*args, **kwargs)


    def dealWithNewFlow(self, flow):
        """
        Implements the abstract method
        """
        # In general, this won't be True that often...
        ecmp = False
        
        # Get the flow prefixes
        src_prefix = flow['src'].network.compressed
        dst_prefix = flow['dst'].network.compressed
        
        # Get the current path from source to destination
        currentPaths = self.getActivePaths(src_prefix, dst_prefix)

        t = time.strftime("%H:%M:%S", time.gmtime())
        to_print = "%s - dealWithNewFlow(): Current paths for flow: %s\n"
        log.info(to_print%(t, str(self.toLogRouterNames(currentPaths))))

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

        # Check if flow can be allocated. Otherwise, call allocation
        # algorithm.
        if self.canAllocateFlow(flow, currentPaths):
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): Flow can be ALLOCATED in current paths\n"%t)
            self.addAllocationEntry(dst_prefix, flow, currentPaths)

        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): Flow CAN'T be allocated in current paths\n"%t)
        
            # Otherwise, call the subclassed method to properly
            # allocate flow to a congestion-free path
            self.flowAllocationAlgorithm(dst_prefix, flow, currentPaths)

            
    def flowAllocationAlgorithm(self, dst_prefix, flow, initial_paths):
        """
        """
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - flowAllocationAlgorithm(): Greedy Algorithm started\n"%t)
        start_time = time.time()
        
        # Remove edges that can't allocate flow from graph
        required_size = flow['size']
        tmp_nw = self.getNetworkWithoutFullEdges(self.initial_graph, required_size)
        
        try:
            # Calculate new default dijkstra path
            shortest_congestion_free_path = self.getDefaultDijkstraPath(tmp_nw, flow)

            # Remove the destination subnet node from the path
            shortest_congestion_free_path = shortest_congestion_free_path[:-1]
            
        except nx.NetworkXNoPath:
            # There is no congestion-free path to allocate all traffic to dst_prefix
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - flowAllocationAlgorithm(): Flow can't be allocated in the network\n"%t)
            log.info("\tAllocating it the default Dijkstra path for the moment...\n")
            log.info("\tBut we should look for longer prefix fibbing...\n")
            
            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, initial_paths)
            log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(dst_prefix))
            log.info("\t* Paths (%s): %s\n"%(len(path_list), str([self.toLogRouterNames(path) for path in initial_paths])))
            # Here, we should search fibbing for longer prefixes!!!!!!!!
            pass
        
        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - flowAllocationAlgorithm(): Found path that can allocate flow\n"%t)
            log.info("\t\t* Path (readable): %s\n"%str(self.toLogRouterNames(shortest_congestion_free_path)))
            log.info("\t\t* Path (ips): %s\n"%str(shortest_congestion_free_path))

            #dtp = self.toLogDagNames(dag)
            #t = time.strftime("%H:%M:%S", time.gmtime())
            #log.info("%s - flowAllocationAlgorithm(): Initial DAG\n"%t)
            #log.info("%s\n"%str(dtp.edges(data=True)))

            # Rename
            scfp = shortest_congestion_free_path
            
            if not self.longerPrefixNeeded(dst_prefix, initial_paths, [scfp]):

                # Modify destination DAG
                dag = self.getCurrentDag(dst_prefix)
                
                # Get edges of new found path
                new_path_edges = set(zip(scfp[:-1], scfp[1:]))
                
                # Deactivate old edges from initial path nodes (won't
                # be used anymore)
                for node in scfp:
                    # Get active edges of node
                    active_edges = self.getActiveEdges(dag, node)
                    for a_e in active_edges:
                        if a_e not in new_path_edges:
                            dag = self.switchDagEdgesData(dag, [(a_e)], active=False)
                            
                
                # Add new edges from new computed path
                dag = self.switchDagEdgesData(dag, [scfp], active=True)
            
                # This complete DAG goes to the prefix-dag data attribute
                self.setCurrentDag(dst_prefix, dag)
                
                # Retrieve only the active edges to force fibbing
                final_dag = self.getActiveDag(dst_prefix)
            
                #dtp = self.toLogDagNames(final_dag)
                #t = time.strftime("%H:%M:%S", time.gmtime())
                #log.info("%s - flowAllocationAlgorithm(): Final DAG\n"%t)
                #log.info("%s\n"%str(dtp.edges(data=True)))

                # Force DAG for dst_prefix
                self.sbmanager.add_dag_requirement(dst_prefix, final_dag)
            
                # Allocate flow to Path. It HAS TO BE DONE after changing the DAG...
                self.addAllocationEntry(dst_prefix, flow, [shortest_congestion_free_path])

                # Log 
                t = time.strftime("%H:%M:%S", time.gmtime())
                to_print = "%s - flowAllocationAlgorithm(): "
                to_print += "Forced forwarding DAG in Southbound Manager\n"
                log.info(to_print%t)
                
            else:
                # We should get a longer prefix for the current flow
                # that the one advertised in the routers. And then
                # calculate allocation again for that more specific
                # prefix.

                # We should be aware that that new prefix may include
                # also previously allocated flows
                t = time.strftime("%H:%M:%S", time.gmtime())
                to_print = "%s - flowAllocationAlgorithm(): "
                to_print += "Longer Prefix FIBBING needed\n"
                log.info(to_print%t)
                log.info("\t Doing nothing for the moment...\n")
                pass
                        
        # Do this allways
        elapsed_time = time.time() - start_time
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - flowAllocationAlgorithm(): Greedy Algorithm Finished\n"%t)
        log.info("\t* Elapsed time: %.3fs\n"%float(elapsed_time))


    def longerPrefixNeeded(self, dst_prefix, initial_paths, new_paths):
        """Given the initial paths and the new calculated path, checks if the
        new allocation collides with already existing flows and thus
        we need longer prefix fibbing.
        
        :param dst_prefix: subnet prefix

        :param initial_paths: list of paths. Paths as list of nodes

        :new_path: path as list of nodes"""

        # Get current DAG
        currentDag = self.getCurrentDag(dst_prefix)

        # Get ongoing flows for dst_prefix
        allocated_flows = self.getAllocatedFlows(dst_prefix)

        # Collect edges for which there are flows ongoing
        ongoing_flows_edges = set()
        for (flow, path_list) in allocated_flows:
            for path in path_list:
                ongoing_flows_edges.update(ongoing_flows_edges.union(zip(path[:-1], path[1:])))
                    
        # Collect edges initial_path
        edges_initial_paths = set()
        for path in initial_paths:
            edges_initial_paths.update(edges_initial_paths.union(zip(path[:-1], path[1:])))

        if edges_initial_paths.intersection(ongoing_flow_edges) != set():
            # Longer prefix fibbing is needed
            return True
        else:
            # Collect edges of new paths
            edges_new_paths = set()
            for path in new_paths:
                edges_new_paths.update(edges_new_paths.union(zip(path[:-1], path[1:])))

            # Check if edges that should be deactivated have ongoing
            # flows too
            for path in new_path:
                for node in path:
                    active_edges = self.getActiveEdges(currentDag, node)
                    for edge in active_edges:
                        if edge in ongoing_flows_edges and edge not in edges_new_paths:
                            return True
            return False

        
if __name__ == '__main__':
    log.info("SIMPLE PATH LOAD BALANCER CONTROLLER\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    lb = SimplePathLB()
    lb.run()
