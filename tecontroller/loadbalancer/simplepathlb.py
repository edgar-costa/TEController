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
        # Get the destination network prefix
        dst_prefix = flow['dst'].network
        # Get source hostname
        src_hostname = self._db_getNameFromIP(flow['src'].compressed) 
        # Get source attached router
        (src_router_name, src_router_id) = self._db_getConnectedRouter(src_hostname)

        # Get default dijkstra path
        defaultPath = self.getDefaultDijkstraPath(self.network_graph, flow)
        
        # Get length of the default dijkstra shortest path
        defaultLength = self.getPathLength(defaultPath)
        
        # Get all paths with length equal to the defaul path length
        default_paths = self._getAllPathsLim(self.network_graph, src_router_id, dst_prefix.compressed, defaultLength)

        log.info("defaultPath: %s\n"%self.toRouterNames(defaultPath))
        log.info("defaultLength: %d\n"%defaultLength)
        log.info("default_paths: %s\n"%(str([self.toRouterNames(r) for r in default_paths])))

        ecmp = False
        if len(default_paths) > 1:
            # ECMP is happening
            ecmp = True
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): ECMP is ACTIVE\n"%t)
        elif len(default_paths) == 1:
            ecmp = False
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): ECMP is NOT active\n"%t)
        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): ERROR\n"%t)

        is_fibbed = False
        if ecmp == True:
            # So far it means that it is not fibbed! since we induced a simple path DAG
            is_fibbed = False
        else:
            # It means there is only one path. NO ECMP
            # Check if calculated path was previously fibbed
            is_fibbed = self.isFibbedPath(defaultPath) 

            if is_fibbed == True:
                log.info("dealWithNewFlow(): Found fibbed path\n")
                log.info("Checking in allocation table...: %s\n"%str(self.flow_allocation[dst_prefix].items()))
                ###
                # Something must be done here: maybe retreive the saved path!?
            else:
                pass
            
        #########################################
        # Check if flow can be allocated. Otherwise, call allocation
        # algorithm.
        if self.canAllocateFlow(flow, default_paths):
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): default Dijkstra path/s can allocate flow\n"%t)

            # Allocate new flow and default paths to destination prefix
            self.addAllocationEntry(dst_prefix, flow, default_paths)
        else:
            # Otherwise, call the subclassed method
            self.flowAllocationAlgorithm(dst_prefix, flow, default_paths)
        ##########################################
            
    def flowAllocationAlgorithm(self, dst_prefix, flow, initial_paths):
        """
        """
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - flowAllocationAlgorithm(): Greedy Algorithm started\n"%t)
        start_time = time.time()
        
        # Remove edges that can't allocate flow from graph
        required_size = flow['size']
        tmp_nw = self.getNetworkWithoutFullEdges(self.network_graph, required_size)
        
        try:
            # Calculate new default dijkstra path
            shortest_congestion_free_path = self.getDefaultDijkstraPath(tmp_nw, flow)

        except nx.NetworkXNoPath:
            # There is no congestion-free path to allocate all traffic to dst_prefix
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - flowAllocationAlgorithm(): Flow can't be allocated in the network\n"%t)
            log.info("\tAllocating it the default Dijkstra path...\n")
            
            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, initial_paths)
            log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(dst_prefix.compressed))
            log.info("\t* Paths (%s): %s\n"%(len(path_list), str([self.toRouterNames(path) for path in initial_paths])))

        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - flowAllocationAlgorithm(): Found path that can allocate flow\n"%t)
            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, [shortest_congestion_free_path])
            # Call to FIBBING Controller should be here
            self.sbmanager.simple_path_requirement(dst_prefix.compressed,
                                                   [r for r in shortest_congestion_free_path
                                                    if self.isRouter(r)])

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
