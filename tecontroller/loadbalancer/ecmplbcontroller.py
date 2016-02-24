class ECMPLBController(LBController):
    def __init__(self, *args, **kwargs):
        super(ECMPLBController, self).__init__(*args, **kwargs)

    def getNetworkWithoutFullEdges(self, network_graph, flow_size):
        """Returns a nx.DiGraph representing the network graph without the
        edge that can't allocate a flow of flow_size.

        :param flow_size: Attribute of a flow defining its size (in bytes).
        """
        ng_temp = copy.deepcopy(network_graph)
        
        full_edges = [ng_temp.remove_edge(x,y) for (x, y, data) in
                      network_graph.edges(data=True) if
                      data.get('capacity') and data.get('capacity') <=
                      flow_size]
        
        log.info("LBC: Edges that can't allocate flow of size: %d\n%s\n"%(flow_size, str(network_graph.difference(ng_temp))))

        return ng_temp

    
    def flowAllocationAlgorithm(self, dst_prefix, flow, initial_path):
        """
        Implements abstract method.
        """
        
        log.info("LBC: Greedy Algorithm started\n")
        start_time = time.time()
        i = 1

        # Remove edge that can't allocate flow from graph
        tmp_nw = self.getNetworkWithoutFullEdges(self.network_graph, flow['size'])
        try:
            # Calculate new default dijkstra path
            shortest_congestion_free_path = self.getDefaultDijkstraPath(tmp_nw, flow)

        except nx.NetworkXNoPath:
            # There is no congestion-free path between src and dst
            log.info("LBC: The flow can't be allocated in the network\n")
            log.info("     Allocating it the default Dijkstra path...\n")

            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, [initial_path])
            log.info("      * Dest_prefix: %s\n"%(str(dst_prefix.compressed)))
            log.info("      * Path: %s\n"%(str(initial_path)))

        else:
            log.info("LBC: Found path that can allocate flow\n")
            # Allocate flow to Path
            self.addAllocationEntry(dst_prefix, flow, [shortest_congestion_free_path])
            # Call to FIBBING Controller should be here
            log.info("      * Dest_prefix: %s\n"%(str(dst_prefix.compressed)))
            log.info("      * Path: %s\n"%(str(shortest_congestion_free_path)))
            self.sbmanager.simple_path_requirement(dst_prefix.compressed,
                                                   [r for r in
                                                    shortest_congestion_free_path
                                                    if r in
                                                    self.routers_to_ip.values()])
            log.info("LBC: Fored forwarding DAG in Southbound Manager\n")

        # Do anyways
        elapsed_time = time.time() - start_time
        log.info("LBC: Greedy Algorithm Finished\n")
        log.info("      * Elapsed time: %ds\n"%elapsed_time)
        log.info("      * Iterations: %ds\n"%i)


