#!/usr/bin/python

from tecontroller.loadbalancer.simplepathlb import SimplePathLB
from tecontroller.res import defaultconf as dconf

from fibbingnode.misc.mininetlib import get_logger

import networkx as nx
import threading
import time
import math

log = get_logger()
lineend = "-"*100+'\n'

class ECMPLB(SimplePathLB):
    """Implements an load balancing algorithm that not only forces simple
    path requirements in the network, but when the lb fails to allocate
    a flow, uses fibbing to force ECMP to find other possible allocations
    for the flow, or, i.e: move part of the traffic from the congested links.

    Simple overview of the algorithm:
    
    """
    def __init__(self, *args, **kwargs):
        super(ECMPLB, self).__init__(*args, **kwargs)

    def ecmpAlgorithm(self, prefix, flow):
        pass

    def getPrefixStatistics(self, prefix):
        for prefix in self.ospf_prefixes:

    def ecmpAlgorithmOLD(self, dst_prefix, flow):
        """
        Pseudocode:

        rankedPaths = self.getAllPaths(self.network_graph, flow.src.attached_router, dst_prefix)
        for path in rankedPaths:
            minCapacity = self.getMinCapacity(path)
            n_paths_needed = flow.size/minCapacity
            temp_network_graph = self.getNetworkWithoutFullEdges(self.networ_graph, minCapacity)
            all_capable_paths = self.getAllPaths(temp_network_graph, flow.src.attached_router, dst_prefix)
            if len(all_capable_paths) < n_paths_needed:
                continue
            else:
                self.allocateFlowToECMPPaths(flow, all_capable_paths[:n_paths_needed])
        """
        start_time = time.time()
        
        t = time.strftime("%H:%M:%S", time.gmtime())
        to_print = "%s - ecmpAlgorithm() started...\n"
        log.info(to_print%t)

        # Get source hostname
        src_hostname = self._db_getNameFromIP(flow['src'].compressed) 

        # Get source attached router
        (src_router_name, src_router_id) = self._db_getConnectedRouter(src_hostname)
        
        # Get all paths from src to dst ranked by length
        rankedPaths = self.getAllPathsRanked(self.network_graph, src_router_id, dst_prefix)
        
        found_allocation = False
        for (path, length) in rankedPaths:
            minCapacity = self.getMinCapacity(path)

            # We get do the following to avoid congestion
            (minu, minv) = self.getMinCapacityEdge(path)
            minEdgeBw = self.network_graph.get_network_data(minu, minv)
            minEdgeBw = minEdgeBw.get('bw', None)
            if minEdgeBw:
                # To avoid congestion, we assume here that around 5%
                # of the link's bandwidth is consumed capacity that we
                # do not control
                minCapacity_aux = (minCapacity - (minEdgeBw*0.05))
            else:
                minCapacity_aux = minCapacity
                
            n_paths_needed = math.ceil(flow['size']/float(minCapacity_aux))
            tmp_network_graph = self.getNetworkWithoutFullEdges(self.network_graph, minCapacity_aux)
            capable_paths = self.getAllPathsRanked(tmp_network_graph, src_router_id, dst_prefix)
            if len(capable_paths) < n_paths_needed:
                continue
            else:
                found_allocation = True
                self.addAllocationEntry(dst_prefix, flow, capable_paths[:n_paths_needed])

        if not found_allocation:
            log.info("\tNo congestion-free ECMP allocation could be found\n")
            log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(prefix.compressed))
            log.info("\t* Paths (%s): %s\n"%(len(path_list), str([self.toRouterNames(path) for path in path_list])))
            log.info("\t* Flow: %s\n"%self.toFlowHostnames(flow))

        t = time.strftime("%H:%M:%S", time.gmtime())
        to_print = "%s - ecmpAlgorithm() finished after %.3f seconds\n"%(t, time.time()-start_time)
        log.info(to_print)
        
                
if __name__ == '__main__':
    log.info("ECMP-AWARE LOAD BALANCER CONTROLLER\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    lb = ECMPLB()
    lb.run()
