class GreedyLBController(LBController):
    def __init__(self, *args, **kwargs):
        super(GreedyLBController, self).__init__(*args, **kwargs)


    def flowAllocationAlgorithm(self, dst_prefix, flow, initial_path):
        """This is the abstract method. Here we decide which version of the
        algorithm is called.
        """
        #self.flowAllocationAlgorithm1(dst_prefix, flow, initial_path)
        self.flowAllocationAlgorithm2(dst_prefix, flow, initial_path)
        
    def flowAllocationAlgorithm1(self, dst_prefix, flow, initial_path):
        """
        Implements abstract method.
        """
        log.info("LBC: Greedy Algorithm started\n")
        start_time = time.time()
        cant_be_allocated = False
        i = 1

        # Copy initial path
        initial_path_c = copy.copy(initial_path)
        
        # Remove edge with least capacity from path
        (ex, ey) = self.getMinCapacityEdge(initial_path_c)
        tmp_nw = self.getNetworkWithoutEdge(self.network_graph, ex, ey)

        # Calculate new default dijkstra path
        next_default_dijkstra_path = self.getDefaultDijkstraPath(tmp_nw, flow)
        
        # Repeat it until path is found that can allocate flow or no more
        while not self.canAllocateFlow(flow, next_default_dijkstra_path):
            i = i + 1
            initial_path_c = next_default_dijkstra_path
            # Remove edge with minimum capacity
            (ex, ey) = self.getMinCapacityEdge(initial_path_c)
            tmp_nw = self.getNetworkWithoutEdge(tmp_nw, ex, ey)
            log.info("    * Edge removed: %s\n"%str((ex, ey)))
            
            try:
                # Calculate new path without removed edge
                next_default_dijkstra_path = self.getDefaultDijkstraPath(tmp_nw, flow)
            except nx.NetworkXNoPath:
                # There is no congestion-free path between src and dst
                log.info("LBC: The flow can't be allocated in the network\n")
                log.info("     Allocating it the default Dijkstra path...\n")
                cant_be_allocated = True
                break

        if cant_be_allocated == False:
            # Allocate flow to found congestion-free dijkstra path
            self.addAllocationEntry(dst_prefix, flow, [next_default_dijkstra_path])

            # Call to FIBBING Controller should be here
            self.sbmanager.simple_path_requirement(dst_prefix.compressed,
                                                   [r for r in
                                                    next_default_dijkstra_path
                                                    if r in
                                                    self.routers_to_ip.values()])
            log.info("LBC: Fored forwarding DAG in Southbound Manager\n")
            log.info("      * Dest_prefix: %s\n"%(str(dst_prefix.compressed)))
            log.info("      * Path: %s\n"%(str(next_default_dijkstra_path)))

        else:
            # Allocate flow to initial path: Path
            self.addAllocationEntry(dst_prefix, flow, [initial_path])
            log.info("      * Dest_prefix: %s\n"%(str(dst_prefix.compressed)))
            log.info("      * Path: %s\n"%(str(initial_path)))
            
        elapsed_time = time.time() - start_time
        log.info("LBC: Greedy Algorithm Finished ")
        log.info("      * Elapsed time: %ds\n"%elapsed_time)
        log.info("      * Iterations: %ds\n"%i)
            

            
    def flowAllocationAlgorithm2(self, dst_prefix, flow, initial_path):
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



