import networkx as nx
import itertools as it
import random

class Evaluation(object):
    def __init__(self, edgeCreationProb = 0.5):
        # Probability of edge creation
    	self.p = edgeCreationProb

    def generateGraph(self, n_nodes, max_OSPF_weight, max_available_capacity):
        """
    	"""
    	# Generate random nodes and edges
    	graph = nx.gnp_random_graph(n_nodes, self.p)
        
    	# Generate random OSPF weights and capacities
    	taken = []
    	for (x,y) in graph.edges_iter():
            # Generate capacities first
            capacity = random.randint(2, max_available_capacity)
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

    def pickRandomNode(self, graph):
    	nodes_copy = graph.nodes()[:]
    	random.shuffle(nodes_copy)
    	return nodes_copy[0]
        
    def generateSources(self, graph, egress_node, max_flow_size):
        """
        """
        flow_sizes = []
        flow_paths = []
        probCong = self.ExactCongestionProbability(graph, flow_paths, flow_sizes)
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
            probCong = self.ExactCongestionProbability(graph, flow_paths, flow_sizes)
            
        # Accumulate all sources
        all_sources = [(flow_sizes[i], flow_paths[i]) for i in range(len(flow_sizes))]        
        return all_sources

    def makePlot(self):
        """
        """
        pass
        
    def run(self):
        """
        """
        # Generate random dag
        graph = self.generateGraph(n_nodes=20, max_OSPF_weight=5, max_available_capacity=10)
        
        # Pick random destination
        egressNode = self.pickRandomNode(graph)
        
        # Generate random sources
        sources = self.generateSources(graph, egress_node=egressNode, max_flow_size=2)

        # Get flow triggering congestion
        trigger_flow = sources[-1]
        # Extract flow and path_list
        (tf, tf_pl) = trigger_flow

        # Ingress node for triggering flow
        ingressNode = tf_pl[0][0]

        import ipdb; ipdb.set_trace()
        # Compute all possible ir->er DAGs
        all_dags = getAllPossibleDags(graph, ingressNode, egressNode)

        # Results are stored in a dict
        results = {}

        # Sample the space
        total_samples = len(all_dags)
        for n in range(total_samples):
            print('*** %d/%d samples'%(n, total_samples))
            # Do it 10 times and take average
            pcs = []
            for times in range(10):
                # Shuffle all_dags
                random.shuffle(all_dags)

                # Take n random dags from all_dags
                samples = all_dags[:n]
                
                # Compute congestion probability for each sample
                tmp_pcs = []
                for new_dag in samples:
                    # Compute congestion probability
                    pc = self.computeCongestionProbability(graph, new_dag, ingressNode, egressNode, sources)
                    
                    # Append it to tmp_pcs
                    tmp_pcs.append((new_dag, pc))

                # Take minimum
                minPc = min(tmp_pcs, key=lambda x: x[1])

                # Append it to pcs
                pcs.append(minPc)
                
                # Log a bit
                print("    %d\tminPc: %.2f"%(times, minPc))
                
            # Convert to numpy array
            pcs = np.asarray(pcs)

            # Add results to dict
            results[n] = {'pcs': pcs} 
            

    def computeCongestionProbability(self, graph, new_dag, ingress_node, egress_node, sources):
        """
        """
        # Compute new all-nodes DAG

        # Recompute sources paths

        # Compute congestion probability Pc
        
        #return pc
        pass

    def _getAllPathsLim(self, igp_graph, start, end, k, path=[], len_path=0, die=False):
        """Recursive function that finds all paths from start node to end
        node with maximum length of k.
        """
        if die == False:
            # Accumulate path length first
            if path == []:
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


    def ExactCongestionProbability(self, all_dag, flow_paths, flow_sizes):
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

if __name__ == '__main__':
#    import ipdb; ipdb.set_trace()
    evaluation = Evaluation()
    evaluation.run()
