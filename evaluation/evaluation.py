import networkx as nx
import itertools as it
import numpy as np
import random
import time

class Evaluation(object):
    def __init__(self, nodes=5, edgeCreationProb = 0.5):
        # Number of nodes in the network
        self.n = nodes
        # Probability of edge creation
    	self.p = edgeCreationProb

        print("*** Evaluation: %d nodes, %f prob."%(self.n, self.p))

    def generateGraph(self, max_OSPF_weight, max_available_capacity):
        """
    	"""
        # Generate random nodes and edges
    	graph_tmp = nx.gnp_random_graph(self.n, self.p, directed=True)

        # Generate reverse edges
        graph = graph_tmp.copy()
        taken = []
        for (x,y) in graph_tmp.edges_iter():
            if (x,y) not in taken:
                graph.add_edge(y,x)

        # Generate random OSPF weights and capacities
    	taken = []
        for (x,y) in graph.edges_iter():
            # Generate capacities first
            capacity = random.randint(5, max_available_capacity)
            graph[x][y]['capacity'] = capacity
            
            # Generate OSPF weights
            if (x,y) not in taken:
                # Generate random weight
                weight = random.randint(1, max_OSPF_weight)
                graph[x][y]['weight'] = weight
                graph[y][x]['weight'] = weight
                taken.append((x,y))
                taken.append((y,x))

        return graph

    @staticmethod
    def pickRandomNode(graph):
        nodes_copy = graph.nodes()[:]
        random.shuffle(nodes_copy)
        return nodes_copy[0]
        
    def generateSources(self, graph, egress_node, max_flow_size):
        """
        """
        flow_sizes = []
        flow_paths = []
        probCong = self.exactCongestionProbability(graph, flow_paths, flow_sizes)
        while probCong < 0.75:
            # Add new flow
            # Pick random ingress node
            ingress_node = self.pickRandomNode(graph)

            # Pick random flow siez
            flow_size = random.randint(1, max_flow_size)

            # Calculate all default OSPF paths for flow

            # Get first length of shortest dijkstra path
            ospf_path_len = nx.dijkstra_path_length(graph, ingress_node, egress_node)
           
            # Compute all equal cost paths
            all_paths = self._getAllPathsLim(graph, ingress_node, egress_node, ospf_path_len)

            # Update flow sizes and flow paths
            flow_sizes.append(flow_size)
            flow_paths.append(all_paths)

            # Calculate new probCong
            probCong = self.exactCongestionProbability(graph, flow_paths, flow_sizes)
            
        # Accumulate all sources
        all_sources = [(flow_sizes[i], flow_paths[i]) for i in range(len(flow_sizes))]        
        return all_sources

    @staticmethod
    def makePlot():
        """
        """
        pass
        
    
    def run(self):
        """
        """
        # Generate random dag
        graph = self.generateGraph(max_OSPF_weight=5, max_available_capacity=10)
        
        # Pick random destination
        egressNode = self.pickRandomNode(graph)
        print("*** Egress node chosen: %d"%egressNode)
        
        # Generate random sources
        sources = self.generateSources(graph, egress_node=egressNode, max_flow_size=2)
        print("*** Number of sources: %d"%(len(sources)))

        # Get flow triggering congestion
        trigger_flow = sources[-1]
        # Extract flow and path_list
        (tf, tf_pl) = trigger_flow

        # Ingress node for triggering flow
        ingressNode = tf_pl[0][0]
        print("*** Source at ingress node %d creates congestion"%ingressNode)

        # Compute all possible ir->er DAGs
        all_dags = self.getAllPossibleDags(graph, ingressNode, egressNode)

        # Compute current all-nodes->er DAG
        all_nodes_dag = self.computeAllNodesDag(graph, egressNode)

        # Results are stored in a dict
        results = {}

        # Sample the space
        total_samples = len(all_dags)

        for n in range(1, total_samples+1):
            print('*** %d/%d samples'%(n, total_samples))
            # Do it 10 times and take average
            pcs = []
            for times in range(5):
                # Shuffle all_dags
                random.shuffle(all_dags)

                # Take n random dags from all_dags
                samples = all_dags[:n]

                # Compute congestion probability for each sample
                tmp_pcs = []
                for new_dag in samples:

                    # Compute congestion probability
                    pc = self.computeCongestionProbability(graph, all_nodes_dag, new_dag, sources)

                    # Append it to tmp_pcs
                    tmp_pcs.append((new_dag, pc))

                # Take minimum
                minPc = min(tmp_pcs, key=lambda x: x[1])

                # Append it to pcs
                pcs.append(minPc[1])

            # Convert to numpy array
            pcs = np.asarray(pcs)
            
            # Log a bit
            print("    minPc: %.2f +/- %.2f"%(pcs.mean(), pcs.std()))

            # Add results to dict
            results[n] = {'pcs': pcs} 

        import ipdb; ipdb.set_trace()

    def computeAllNodesDag(self, graph, egress_node):
        """
        """
        all_nodes_dag = nx.DiGraph()
        edges_set = set()
        for node in graph.nodes_iter():
            if node != egress_node:
                # Get length of the shortest path
                defaultLen = nx.dijkstra_path_length(graph, node, egress_node)
                
                # Get all paths with length equal to the defaul path length
                default_paths = self._getAllPathsLim(graph, node, egress_node, defaultLen)
                
                # Update edges
                action = [edges_set.update({edge}) for p in default_paths for edge in zip(p[:-1], p[1:])]

        # Add edges forcing found paths
        all_nodes_dag.add_edges_from(list(edges_set))
        return all_nodes_dag


    def recomputeAllSourcesDag(self, all_dag, new_ridx_dag):
        """
        Given the initial all_routers_dag, and the new chosen ridxDag, we compute
        the newly created all_routers_dag merging the previous one while forcing the
        new ridxDag.
        """

        # Add 'flag' in new ridx dag
        edges = new_ridx_dag.edges()
        ridx_dag = nx.DiGraph()
        ridx_dag.add_edges_from(edges, flag=True)
        
        # Compose it with all_dag
        new_adag = nx.compose(all_dag, ridx_dag)

        # Iterate new ridx nodes. Remove those outgoing edges from the same node 
        # in all_dag that do not have 'flag'.
        final_all_dag = new_adag.copy()

        # Get edges to remove
        edges_to_remove = [(x, y) for node in new_ridx_dag.nodes() for
                           (x, y, data) in new_adag.edges(data=True)
                           if node == x and not data.get('flag')]

        # Remove them
        final_all_dag.remove_edges_from(edges_to_remove)
        
        # Return modified all_dag
        return final_all_dag

    def computeCongestionProbability(self, graph, all_sources_dag, new_ridx_dag, sources):
        """
        """
        # Compute new all-nodes DAG
        new_adag = self.recomputeAllSourcesDag(all_sources_dag, new_ridx_dag)
        
        # Recompute sources paths
        new_sources = self.recomputeSourcesPaths(new_adag, sources)

        # Extract new flow paths and sizes
        flow_paths = [pl for (f, pl) in sources]
        flow_sizes = [f for (f, pl) in sources]

        # Compute congestion probability Pc
        pc = self.exactCongestionProbability(graph, flow_paths, flow_sizes)

        return pc

    def recomputeSourcesPaths(self, new_adag, sources):
        # Get egress node
        egressNode = sources[0][1][0][-1]

        # Accumulate new sources here
        new_sources = []

        for (f, pl) in sources:
            # Get ingress router
            ingressNode = pl[0][0]
            
            # Compute new path list
            new_pl = self._getAllPathsLimDAG(new_adag, ingressNode, egressNode, k=0)
            
            # Accumulate it in new sources
            new_sources.append((f, new_pl))
            
        return new_sources

    def _getAllPathsLimDAG(self, dag, start, end, k, path=[]):
        """Recursive function that finds all paths from start node to end node
        with maximum length of k.
        
        If the function is called with k=0, returns all existing
        loopless paths between start and end nodes.
        
        :param dag: nx.DiGraph representing the current paths towards
        a certain destination.
        
        :param start, end: string representing the ip address of the
        star and end routers (or nodes) (i.e:
        10.0.0.3).
        
        :param k: specified maximum path length (here means hops,
        since the dags do not have weights).
        
        """
        # Accumulate nodes in path
        path = path + [start]
        
        if start == end:
            # Arrived to the end. Go back returning everything
            return [path]
            
        if not start in dag:
            return []
            
        paths = []
        for node in dag[start]:
            if node not in path: # Ommiting loops here
                if k == 0:
                    # If we do not want any length limit
                    newpaths = self._getAllPathsLimDAG(dag, node, end, k, path=path)
                    for newpath in newpaths:
                        paths.append(newpath)
                elif len(path) < k+1:
                    newpaths = self._getAllPathsLimDAG(dag, node, end, k, path=path)
                    for newpath in newpaths:
                        paths.append(newpath)
        return paths



    def _getAllPathsLim(self, igp_graph, start, end, k, path=[], len_path=0, die=False):
        """Recursive function that finds all paths from start node to end
        node with maximum length of k.
        """
        if not die:
            # Accumulate path length first
            if not path:
                len_path = 0
            else:
                last_node = path[-1]
                len_path += igp_graph.get_edge_data(last_node, start)['weight']
                
            # Accumulate nodes in path
            path = path + [start]
        
            if start == end:
                # Arrived to the end. Go back returning everything
                if k == 0:
                    return [path]
                elif len_path < k+1:
                    return [path]
                else:
                    self._getAllPathsLim(igp_graph, start, end, k, path=path, len_path=len_path, die=True)
            
            if not start in igp_graph:
                return []

            paths = []
            for node in igp_graph[start]:
                if node not in path: # Ommiting loops here
                    if k == 0:
                        # If we do not want any length limit
                        newpaths = self._getAllPathsLim(igp_graph, node, end, k, path=path, len_path=len_path)
                        for newpath in newpaths:
                            paths.append(newpath)
                    elif len_path < k+1:
                        newpaths = self._getAllPathsLim(igp_graph, node, end, k, path=path, len_path=len_path)
                        for newpath in newpaths:
                            paths.append(newpath)
            return paths
        else:
            # Recursive call dies here
            pass

    def exactCongestionProbability(self, all_dag, flow_paths, flow_sizes):
        """
        In this case, path_capacities is a list of lists, representing possible flow path/s 
        min available capacities : [[c1, c2], [c2]...]
        and n is a list of flow sizes: [s1, s2, ...]

        Flow to paths bidings are given by the lists indexes.
        
        Returns congestion probability.
        """
        total_samples = 0
        congestion_samples = 0
        for alloc in it.product(*flow_paths):
            # Add sample to total count
            total_samples += 1
            
            # Create copy of all_dag
            adag_c = all_dag.copy()
            
            # Iterate alloc. For each path i in alloc:
            for index, path in enumerate(alloc):
                # Flag variable to break iteration 
                congestion_found = False
                
                # Subtract size of flow i in all_dag
                for (x, y) in zip(path[:-1], path[1:]):
                    cap = adag_c[x][y]['capacity']
                    cap -= flow_sizes[index]
                    adag_c[x][y]['capacity'] = cap
                    
                    #mincap = adag_c[x][y]['mincap']
                    # Perform check: if at some point, available capacity
                    # < 0: break iteration, go to next alloc                    
                    #if cap < mincap:
                    if cap < 0:
                        congestion_found = True
                        break
                        
                if congestion_found:
                    congestion_samples += 1
                    break
                
        return congestion_samples/float(total_samples)

    def getMergedDag(self, start, end, path_list):
        """
        Given a list of paths, returns the loop-free merged DAG
        forcing all (possible) paths in path_list.
        """
        pathsDags = []
        for path in path_list:
            tmp_dag = nx.DiGraph()
            tmp_dag.add_edges_from(zip(path[:-1], path[1:]))
            pathsDags.append(tmp_dag)

        ## Merge them all into one single DAG
        composedDag = nx.compose_all(pathsDags)

        while not nx.is_directed_acyclic_graph(composedDag):
            ## Eliminate loop edges random
            
            # Get simple cycles
            simple_cycles = [c for c in nx.simple_cycles(composedDag)]
            
            for cycle in simple_cycles:
                # Remove cycle edge at random
                cycle_edges = zip(cycle[:-1], cycle[1:])
                random.shuffle(cycle_edges)
                (x,y) = cycle_edges[0]
                if (x,y) in composedDag.edges():
                    composedDag.remove_edge(x, y)
                
        # Compute all paths on randomDag (to eliminate dummy paths)
        all_final_paths = self._getAllPathsLimDAG(composedDag, start, end, k=0)

        pathsDags = []
        for path in all_final_paths:
            tmp_dag = nx.DiGraph()
            tmp_dag.add_edges_from(zip(path[:-1], path[1:]))
            pathsDags.append(tmp_dag)

        finalMergedDag = nx.compose_all(pathsDags)
        return finalMergedDag

    def getAllPossibleDags(self, graph, start, end):
        """
        Given a network graph, and start and end nodes, computes
        a random DAG from start towards end nodes.
        """
        start_time = time.time()

        ## Calculate firts all paths from start to end
        all_paths = self._getAllPathsLim(graph, start, end, k=0)

        print("*** Possible paths from %d to %d: %d"%(start, end, len(all_paths)))

        # Calculate all combinations of possible paths.
        all_path_subsets = []
        action = [all_path_subsets.append(c) for i in range(1, len(all_paths) + 1) for c in
                  list(it.combinations(all_paths, i))]

        #action = [all_path_subsets.append(c) for i in range(1, 3) for c in
        #          list(it.combinations(all_paths, i))]

        print("*** Number of path permutations without repetition: %d"%(len(all_path_subsets)))
        # Compute merge of dags
        allRandomDags = []
        for subset in all_path_subsets:
            mergedDag = self.getMergedDag(start, end, subset)
            allRandomDags.append(mergedDag)

        # Check for duplicates
        uniqueDags = []
        for rdag in allRandomDags:
            # Search first if seen in uniqueDags
            seenUD = [e for e in uniqueDags if rdag.edges() == e[0]]
            if not seenUD:
                # not seen before
                uniqueDags += [(rdag.edges(), 1, rdag)]
            else:
                (ude, fq, ud) = seenUD[0]
                uniqueDags.remove(seenUD[0])
                uniqueDags += [(ude, fq + 1, ud)]

        # Collect unique dags and return them
        allPossibleDags = [c for (a, b, c) in uniqueDags]

        print("*** It took %f seconds to compute all possible DAGs"%(time.time()-start_time))
        print("*** Number of different DAGs found: %d"%(len(allPossibleDags)))
        return allPossibleDags

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--nodes", type=int, help="Number of nodes in the network")
    parser.add_argument("-p", "--probability", type=float, help="Edge probability")
    args = parser.parse_args()

    # Parse input parameters
    if args.nodes and args.probability:
        n = args.nodes
        p = args.probability
        evaluation = Evaluation(n, p)
    else:
        evaluation = Evaluation()
    
    # Run experiment
    evaluation.run()
