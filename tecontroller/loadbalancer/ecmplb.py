#!/usr/bin/python

from tecontroller.loadbalancer.lbcontroller import LBController
from tecontroller.res import defaultconf as dconf

from fibbingnode.misc.mininetlib import get_logger

import networkx as nx
import threading
import time
import math

log = get_logger()
lineend = "-"*100+'\n'


class ECMPLB(LBController):
    """Implements an load balancing algorithm that not only forces simple
    path requirements in the network, but when thede fail to allocate
    a flow, uses fibbing to force ECMP to find other possible
    allocations for the flow.

    Simple overview of the algorithm:
    
    First try to allocate flow in the default path. If it doesn't
    work, try to allocate the whole flow to all possible paths from
    surce to destination.

    If an allocation is still not possible, then get all the possible
    paths from source to destination ranked by increasing distance.
    Iteratively, check remaining space in path and calculate the
    number of other paths needed to perform ECMP towards
    destination. 

    If such number of paths exist, and they can allocate the
    corresponding proportion of the flow, calculate DAG and insert
    it. Otherwise, go to the next path in the ranked list.

    """
    def __init__(self, *args, **kwargs):
        super(ECMPLB, self).__init__(*args, **kwargs)

    def dealWithNewFlow(self, flow):
        """
        """
        # Get the destination network prefix
        dst_prefix = flow['dst'].network

        # Get the default OSFP Dijkstra path
        defaultPath = self.getDefaultDijkstraPath(self.network_graph, flow)
        
        # If it can be allocated, no Fibbing needed
        if self.canAllocateFlow(flow, defaultPath):
            # Log it
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): default Dijkstra path can allocate flow\n"%t)

            # Allocate new flow and default path to destination prefix
            self.addAllocationEntry(dst_prefix, flow, defaultPath)

        else:
            # Otherwise, call the abstract method
            self.flowAllocationAlgorithm(dst_prefix, flow, defaultPath)


    def flowAllocationAlgorithm(self, dst_prefix, flow, initial_path):
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
            # There is no congestion-free path to allocate flow
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - flowAllocationAlgorithm(): Flow can't be allocated in the network in a single path\n"%t)
            log.info("\tCalling the ECMP part of the algorithm...\n")

            # Call the ECMP algorithm
            self.ecmpAlgorithm(dst_prefix, flow)
        else:
            # Found single path to allocate flow
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - flowAllocationAlgorithm(): Found path that can allocate flow\n"%t)
            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, shortest_congestion_free_path)
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

    def ecmpAlgorithm(self, dst_prefix, flow):
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
            if flow in self.flow_allocation[prefix].keys():
                self.flow_allocatoin[prefix][flow] += path_list
            else:
                self.flow_allocatoin[prefix][flow] = path_list

        # Loggin a bit...
        t = time.strftime("%H:%M:%S", time.gmtime())
        to_print = "%s - addAllocationEntry(): "
        to_print += "flow ALLOCATED to Paths\n"
        log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(prefix.compressed))
        log.info("\t* Paths (%s): %s\n"%(len(path_list), str([self.toRouterNames(path) for path in path_list])))
        log.info("\t* Flow: %s\n"%self.toFlowHostnames(flow))
                        
        # Check first how many ECMP paths are there
        ecmp_paths = float(len(path_list))
        for path in path_list:
            edges = [(u,v) for (u,v) in zip(path[:-1], path[1:])]
            for (u, v) in edges:
                data = self.network_graph.get_network_data(u, v)
                capacity = data.get('capacity', None)
                if capacity:
                    # Substract corresponding size
                    data['capacity'] -= (flow.size/float(ecmp_paths))
                    
                else:
                    data_i = self.network_graph.get_network_data(v,u)
                    capacity_i = data_i.get('capacity', None)
                    if capacity_i:
                        # Substract corresponding size
                        data_i['capacity'] -= (flow.size/ecmp_paths)
                        data['capactity'] = data_i.get('capacity')
                    else:
                        to_print += "ERROR: capacity key not found in edge (%s, %s)"
                        log.info(to_print%(t, u, v))
                        #It enters here because it considers as edges the
                        #links between interfaces (ip's) of the routers
                        pass
                    
        # Define the removeAllocatoinEntry thread
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
        log.info("%s - removeAllocationEntry(): Flow REMOVED from Paths\n"%t)
        log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(prefix.compressed))
        log.info("\t* Path: %s\n"%str(self.toRouterNames(path)))
        log.info("\t* Flow: %s\n"%self.toFlowHostnames(flow))

        ecmp_paths = float(len(path_list))
        for path in path_list:
            edges = [(u,v) for (u,v) in zip(path[:-1], path[1:])]
            for (u, v) in edges:
                data = self.network_graph.get_network_data(u, v)
                capacity = data.get('capacity', None)
                if capacity:
                    # Add corresponding size
                    data['capacity'] += (flow.size/float(ecmp_paths))
                    
                else:
                    data_i = self.network_graph.get_network_data(v,u)
                    capacity_i = data_i.get('capacity', None)
                    if capacity_i:
                        # Add corresponding size
                        data_i['capacity'] += (flow.size/ecmp_paths)
                        data['capactity'] = data_i.get('capacity')
                    else:
                        to_print += "ERROR: capacity key not found in edge (%s, %s)"
                        log.info(to_print%(t, u, v))
                        #It enters here because it considers as edges the
                        #links between interfaces (ip's) of the routers
                        pass
                    
        # Remove the lies for the given prefix
        self.removePrefixLies(prefix)

        
if __name__ == '__main__':
    log.info("ECMP-AWARE LOAD BALANCER CONTROLLER\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    lb = ECMPLB()
    lb.run()
