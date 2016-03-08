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
            reversed_set.update({(v,u)})

        return reversed_set

    def getNextNonCollidingPrefix(self, dst_ip, previous_dst_network, new_path_list):
        """
        """
        # get allocated flows for network_object prefix
        dst_prefix = previous_dst_network.compressed
        allocated_flows = self.getAllocatedFlows(dst_prefix)   

        # Calculate which of them are colliding with our new path
        edges_new_pl = set(self.getEdgesFromPathList(new_path_list))

        # Acumulate flow destinations ips for which the flows collide
        # with our path
        ips = []
        for (flow, fpl) in allocated_flows:
            edges_flow = self.getEdgesFromPathList(fpl)
            edges_flow = set(edges_flow)
            edges_flow_r = self.getReversedEdgesSet(edges_flow.copy())
            if edges_flow.intersection(edges_new_pl) == set() and edges_flow_r.intersection(edges_new_pl) == set():
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

        log.info("New prefix len found: /%s to ip: %s\n"%(max_prefix_len[1], str(max_prefix_len[0])))
        if max_prefix_len[0] != None:
            # Return the subnet that includes the ip of the new flow!
            subnets = list(previous_dst_network.subnets(new_prefix=max_prefix_len[1]))
            action = [subnet for subnet in subnets if dst_ip in subnet]
            if len(action) == 1:
                return action[0]
            else:
                log.info("No subnet could be found\n")
                return None
        else:
            return None

        
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
        currentPaths = self.getActivePaths(src_iface.compressed, dst_iface.compressed, dst_prefix)

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

        # Try if new congestion-free path found
        try:
            # Calculate new default dijkstra path
            shortest_congestion_free_path = self.getDefaultDijkstraPath(tmp_nw, flow)

            # Remove the destination subnet hop node from the path
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

            # Will be overwritten if longer prefix is needed
            new_dst_prefix = dst_prefix

            # Check if longer prefix needed
            if self.longerPrefixNeeded(dst_prefix, initial_paths, [scfp]):
                
                # Log it first
                t = time.strftime("%H:%M:%S", time.gmtime())
                to_print = "%s - flowAllocationAlgorithm(): longer prefix fibbing needed\n"
                log.info(to_print%t)

                # Get destination host ip
                dst_ip = flow['dst'].ip
                # Create network object from dst_prefix
                dst_network = ipaddress.ip_network(dst_prefix)
                
                # Get next non-colliding (with ongoing flows) prefix
                new_dst_network = self.getNextNonCollidingPrefix(dst_ip, dst_network, [scfp])

                if new_dst_network == None:
                    # If there are no more specific prefixes... we are
                    # fucked! ECMP part of the algorithm must be
                    # activated
                    raise KeyError("We must deal with that")

                # Extract the prefix string
                new_dst_prefix = new_dst_network.compressed

                # Log it
                log.info("\t* New longer prefix found: %s\n"%new_dst_prefix)

                # Get initial DAG from previously existing parent-prefix
                new_dst_dag = self.getInitialDag(dst_prefix)

                # Log it
                dtp = self.toLogDagNames(new_dst_dag)
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("\* Initial dag for new prefix:\n"%t)
                log.info("\t\t%s\n\n"%str(dtp.edges(data=True)))
                
                # Set it to the new found prefix
                self.setCurrentDag(new_dst_prefix, new_dst_dag)

            else:
                # Log it first
                t = time.strftime("%H:%M:%S", time.gmtime())
                to_print = "%s - flowAllocationAlgorithm(): longer prefix NOT needed\n"
                log.info(to_print%t)
                
            # Modify destination DAG
            dag = self.getCurrentDag(new_dst_prefix)
                
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
            self.setCurrentDag(new_dst_prefix, dag)
                
            # Retrieve only the active edges to force fibbing
            final_dag = self.getActiveDag(new_dst_prefix)

            # Log it
            dtp = self.toLogDagNames(final_dag)
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("\* Final modified dag for new prefix: the one with which we fib the prefix\n"%t)
            log.info("\t\t%s\n\n"%str(dtp.edges(data=True)))
            
            # Force DAG for dst_prefix
            self.sbmanager.add_dag_requirement(new_dst_prefix, final_dag)
            
            # Allocate flow to Path. It HAS TO BE DONE after changing the DAG...
            self.addAllocationEntry(new_dst_prefix, flow, [scfp])

            # Log 
            t = time.strftime("%H:%M:%S", time.gmtime())
            to_print = "%s - flowAllocationAlgorithm(): "
            to_print += "Forced forwarding DAG in Southbound Manager\n"
            log.info(to_print%t)
                
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

        if edges_initial_paths.intersection(ongoing_flows_edges) != set():
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
