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
        log.info(to_print%(t, str(self.toRouterNames(currentPaths))))

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
            log.info("\tAllocating it the default Dijkstra path...\n")
            
            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, initial_paths)
            log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(dst_prefix))
            log.info("\t* Paths (%s): %s\n"%(len(path_list), str([self.toRouterNames(path) for path in initial_paths])))

        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - flowAllocationAlgorithm(): Found path that can allocate flow\n"%t)
            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, [shortest_congestion_free_path])

            # Modify destination DAG
            dag = self.getCurrentDag(dst_prefix)
            
            dtp = self.toDagNames(dag)
            log.info("INITIAL_DAG: %s\n"%str(dtp.edges(data=True)))

            # Remove edges from initial paths
            dag = self.turnEdgesInactive(dag, initial_paths)

            # Add new edges from new computed path
            dag = self.turnEdgesActive(dag, [shortest_congestion_free_path])

            # This complete DAG goes to the database
            self.setCurrentDag(dst_prefix, dag)

            # Retrieve only the active edges to force fibbing
            final_dag = self.getActiveDag(dst_prefix)
            
            dtp = self.toDagNames(final_dag)
            log.info("FINAL DAG: %s\n"%str(dtp.edges(data=True)))

            # Call to a FIBBING Controller function should be here
            # instead
            lsa = self.getLiesFromPrefix(dst_prefix)
            if lsa:
                self.sbmanager.remove_lsas(lsa)

            self.sbmanager.fwd_dags[dst_prefix] = final_dag
            self.sbmanager.refresh_lsas()
                
            t = time.strftime("%H:%M:%S", time.gmtime())
            to_print = "%s - flowAllocationAlgorithm(): "
            to_print += "Forced forwarding DAG in Southbound Manager\n"
            log.info(to_print%t)

        # Do this allways
        elapsed_time = time.time() - start_time
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - flowAllocationAlgorithm(): Greedy Algorithm Finished\n"%t)
        log.info("\t* Elapsed time: %.3fs\n"%float(elapsed_time))
                
if __name__ == '__main__':
    log.info("SIMPLE PATH LOAD BALANCER CONTROLLER\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    lb = SimplePathLB()
    lb.run()
