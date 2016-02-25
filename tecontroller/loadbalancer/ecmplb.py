#!/usr/bin/python

from tecontroller.loadbalancer.lbcontroller import LBController
from tecontroller.res import defaultconf as dconf

from fibbingnode.misc.mininetlib import get_logger

import networkx as nx
import threading
import time


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
        pass

    
    def getAllPaths(self, igp_graph, start, end, path=[]):
        """Recursive functoin that returns an ordered list representing all
        paths between node x and y in network_graph. Paths are ordered
        in increasing length.
        
        :param igp_graph: IGPGraph representing the network
        
        :param start: router if of source's connected router

        :param end: compressed subnet address of the destination
                    prefix."""
        path = path + [start]
        if start == end:
            return [path]

        if not start in igp_graph:
            return []

        paths = []
        for node in igp_graph[start]:
            if node not in path: # Ommiting loops here
                newpaths = self.getAllPaths(igp_graph, node, end, path)
                for newpath in newpaths:
                    paths.append(newpath)
        return paths

    def orderByLength(self, paths):
        # Search for path lengths
        ordered_paths = []
        for path in paths:
            pathlen = 0
            for (u,v) in zip(path[:-1], path[1:]):
                if igp_graph.is_router(v):
                    pathlen += igp_graph.get_edge_data(u,v)['weight']
            ordered_paths.append((path, pathlen))
        # Now rank them
        ordered_paths = sorted(ordered_paths, key=lambda x: x[1])
        return ordered_paths
        
    
    def addAllocationEntry(self, prefix, flow, path):
        """Add entry in the flow_allocation table.
        
        :param prefix: is a IPv4Network type

        :param path_list: List of paths (IPNetPath) for which this flow will be
                          multi-pathed towards destination prefix:
                          [[A, B, C], [A, D, C]]"""
        
        if prefix not in self.flow_allocation.keys():
            # prefix not in table
            self.flow_allocation[prefix] = {flow : path}
        else:
            self.flow_allocation[prefix][flow] = path
            
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - addAllocationEntry(): Flow ALLOCATED to Path\n"%t)
        log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(prefix.compressed))
        log.info("\t* Path: %s\n"%str(self.toRouterNames(path)))
        log.info("\t* Flow: %s\n"%self.toFlowHostnames(flow))
        
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
                    data['capacity'] -= flow.size

        # Define the removeAllocationEntry thread
        t = threading.Thread(target=self.removeAllocationEntry, args=(prefix, flow, path))
        # Add handler to list and start thread
        self.thread_handlers[flow] = t
        t.start()


        
    def removeAllocationEntry(self, prefix, flow, path):        
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

        log.info(lineend)
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info("%s - removeAllocationEntry(): Flow REMOVED from Path\n"%t)
        log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(prefix.compressed))
        log.info("\t* Path: %s\n"%str(self.toRouterNames(path)))
        log.info("\t* Flow: %s\n"%self.toFlowHostnames(flow))
        

        for (x, y, data) in self.network_graph.edges(data=True):
            if x in path and y in path and abs(path.index(x)-path.index(y))==1:
                if 'capacity' not in data.keys():
                    #pass: it enters here because it considers as edges
                    #the links between interfaces (ip's) of the routers
                    pass
                else:
                    data['capacity'] += flow['size']
                    
        # Remove the lies for the given prefix
        self.removePrefixLies(prefix)
        
        


if __name__ == '__main__':
    log.info("ECMP-AWARE LOAD BALANCER CONTROLLER\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    lb = ECMPLB()
    lb.run()
