#!/usr/bin/python

from tecontroller.loadbalancer.lbcontroller import LBController
from tecontroller.res import defaultconf as dconf

from fibbingnode.misc.mininetlib import get_logger

import networkx as nx
import ipaddress
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
        
        # Mantains the list of the network prefixes advertised by the OSPF routers
        self.ospf_prefixes = self._fillInitialOSPFPrefixes()

    def _fillInitialOSPFPrefixes(self):
        """
        Fills up the data structure
        """
        prefixes = []
        for host, data in self.hosts_to_ip.iteritems():
            ip_network_object = ipaddress.ip_network(data['iface_router'])
            prefixes.append(ip_network_object)
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

    def getReversedEdgesSet(self, edges_set):
        """Given a set of edges, it returns a set with the reversed edges."""
        reversed_set = set()
        while edges_set != set():
            (u,v) = edges_set.pop()
            reversed_set.update((v,u))

        return reversed_set

    def getNextNonCollidingPrefix(self, dst_ip, dst_network, new_path_list):
        """
        """
        # get allocated flows for network_object prefix
        dst_prefix = dst_network.compressed
        allocated_flows = self.getAllocatedFlows(dst_prefix)   

        # Calculate which of them are colliding with our new path
        edges_new_pl = set(self.getEdgesFromPathList(new_path_list))

        # Acumulate flow destinations ips for which the flows collide
        # with our path
        ips = []
        for (flow, fpl) in allocated_flows:
            edges_flow = set(self.getEdgesFromPathList(fpl))
            edges_flow_r = self.getReversedEdgesSet(edges_flow)
            if edges_flow.intersection(edges_new_pl) != set() or edges_flow_r.intersection(edges_new_pl) != set():
                ips.append(flow['dst'].ip)
            
        # Find the shortest longer prefix that does not collide with flows
        max_prefix_len = (None, 0)
        for ip in ips:
            differ_bit = -1
            xor = int(dst_ip)^int(ip)
            while xor != 0:
                differ_bit += 1
                xor = xor >> 1
                
            if differ_bit == -1:
                log.info("No more longer prefixes that do not collide!\n")
                return None
            
            else:
                prefix_len = 32 - differ_bit
                if prefix_len > max_prefix_len[1]:
                    max_prefix_len = (ip, prefix_len)

        # Return the subnet that includes the ip of the new flow!
        subnets = dst_network.subnets(max_prefix=max_prefix_len)
        action = [subnet for subnet in subnets if dst_ip in subnet]
        if len(action) == 1:
            return action[0]
        else:
            raise KeyError("No subnet could be found")

        
    def getNextLongerPrefix(self, interface_ip, network_object):
        """Given an host interface ip, and the network_object that represents
        the currently advertised network prefix, returns the

        """
        iface_ip = ipaddress.ip_interface(interface_ip).ip
        subnets = list(network_object.subnets())
        for subnet in subnets:
            if iface_ip in subnet:
                return subnet
    
    
    def dealWithNewFlow(self, flow):
        """
        Implements the abstract method
        """
        # In general, this won't be True that often...
        ecmp = False
        
        # Get the flow prefixes
        src_prefix = flow['src'].network.compressed
        dst_ip = flow['dst'].ip
        
        # Get destination longest advertized prefix
        dst_network = self.getCurrentOSPFPrefix(flow['dst'])
        dst_prefix = dst_network.compressed
        
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
            # There is no congestion-free path to allocate flow to dst_prefix
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - flowAllocationAlgorithm(): Flow can't be allocated in the network\n"%t)
            log.info("\tAllocating it the default Dijkstra path for the moment...\n")
            log.info("\tBut we should look for re-arrangement of already allocated flows...\n")
            
            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, initial_paths)
            log.info("\t* Dest_prefix: %s\n"%self._db_getNameFromIP(dst_prefix))
            log.info("\t* Paths (%s): %s\n"%(len(path_list), str([self.toLogRouterNames(path) for path in initial_paths])))
            # Here, we should try to re-arrange flows in a way that
            # all of them can be allocated.
            pass
        
        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - flowAllocationAlgorithm(): Found path that can allocate flow\n"%t)
            log.info("\t\t* Path (readable): %s\n"%str(self.toLogRouterNames(shortest_congestion_free_path)))
            log.info("\t\t* Path (ips): %s\n"%str(shortest_congestion_free_path))

            # Rename
            scfp = shortest_congestion_free_path

            # While no path found that does not collide with already
            # ongoing flows for same destination
            if not self.longerPrefixNeeded(dst_prefix, initial_paths, [scfp]):
                # Get destination host ip
                dst_ip = flow['dst'].ip

                # Get next non-colliding (with ongoing flows) prefix
                new_dst_network = self.getNextNonCollidingPrefix(dst_ip, dst_network, [scfp])
                new_dst_prefix = new_dst_network.compressed

                # Fib new found path with new found destination prefix
                #self.sbmanager.add_dag_requirement()
                
                pass

        
            
                

                
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
