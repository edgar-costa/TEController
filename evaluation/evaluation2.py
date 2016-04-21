import networkx as nx
import itertools as it
import numpy as np
import random
import time
import marshal
import matplotlib.pyplot as plt


class Evaluation(object):
    def __init__(self, nodes=5, edgeCreationProb = 0.2, marshalFile = None):
        # Number of nodes in the network
        self.n = nodes
        # Probability of edge creation
    	self.p = edgeCreationProb
        print("*** Evaluation: %d nodes, %f prob."%(self.n, self.p))

    def generateGraph(self, max_available_capacity):
        """
    	"""
        OSPF_weights = [2, 4]
        
        # Generate random nodes and edges
    	graph_tmp = nx.gnp_random_graph(self.n, self.p)
        while not nx.is_connected(graph_tmp):
            graph_tmp = nx.gnp_random_graph(self.n, self.p)

        # Turn it into directed graph
        graph = graph_tmp.to_directed()

        # Generate random OSPF weights and capacities
    	taken = []
        for (x,y) in graph.edges_iter():
            # Generate capacities first
            capacity = random.randint(5, max_available_capacity)
            graph[x][y]['capacity'] = capacity
            
            # Generate OSPF weights
            if (x,y) not in taken:
                # Generate random weight
                index1 = random.randint(0, 1)
                index2 = random.randint(0, 1)
                graph[x][y]['weight'] = OSPF_weights[index1]
                graph[y][x]['weight'] = OSPF_weights[index2] 
                taken.append((x,y))
                taken.append((y,x))

        return graph

    @staticmethod
    def pickRandomNode(graph):
        nodes_copy = graph.nodes()[:]
        random.shuffle(nodes_copy)
        return nodes_copy[0]
        
    def loadResults(self, filename):
        with open(filename, 'rb') as f:
            results = marshal.load(f)
            return results

    def saveResults(self, results, n, p, id):
        pstr = str(p)
        pstr = pstr.replace('.', '_')
        filename = './results_allocs_%d_%s_%s'%(n, pstr, id)
        with open(filename, 'wb') as f:
            marshal.dump(results, f)
            print("*** Results saved in %s"%filename)


    def generateSourcesThreshold(self, graph, egress_node, max_flow_size, maxCongProb):
        """
        """
        # Create copy of graph
        graph_c = graph.copy()

        # Accumulate sources here
        flow_sizes = []
        flow_paths = []

        # Compute exact probCong
        probCong = self.exactCongestionProbability(graph_c, flow_paths, flow_sizes)

        # Iterate until congestion
        while probCong < maxCongProb:
            ## Add new flow
            # Pick random ingress node
            ingress_node = self.pickRandomNode(graph_c)

            # Pick random flow size
            flow_size = random.randint(1, max_flow_size)
            
            ## Calculate all default OSPF paths for flow
            # Get first length of shortest dijkstra path
            ospf_path_len = nx.dijkstra_path_length(graph_c, ingress_node, egress_node)
           
            # Compute all equal cost paths
            all_paths = self._getAllPathsLim(graph_c, ingress_node, egress_node, k=ospf_path_len)

            # Update flow sizes and flow paths
            flow_sizes.append(flow_size)
            flow_paths.append(all_paths)

            # Calculate new probCong
            probCong = self.exactCongestionProbability(graph_c, flow_paths, flow_sizes)
            
        # Accumulate all sources
        all_sources = [(flow_sizes[i], flow_paths[i]) for i in range(len(flow_sizes))]        
        return (probCong, all_sources)


    def run(self, estimate = True):
        # Results are stored in a dict
        results = {}

        # Generate random dag
        graph = self.generateGraph(max_available_capacity=10)
        
        # Pick random destination
        egressNode = self.pickRandomNode(graph)
        print("*** Egress node chosen: %d"%egressNode)
        
        # Generate random sources
        (probCong, sources) = self.generateSourcesThreshold(graph, egress_node=egressNode, max_flow_size=2, maxCongProb=0.5)
        while probCong > 0.75:
            print "Trying to generate sources..."
            (probCong, sources) = self.generateSourcesThreshold(graph, egress_node=egressNode, max_flow_size=2, maxCongProb=0.5)

        print("*** Number of sources: %d"%(len(sources)))
        print("*** Exact current Pc: %.5f"%(probCong))
        
        # Add it into results
        results['exact'] = probCong

	## Compute the total number of possible allocations 
        # Acumulate path lists
        flow_paths = [pl for (f, pl) in sources]
        total_allocations = len(list(it.product(*flow_paths)))
        print("*** Total number of possible allocations: %d"%(total_allocations))
        
        # Accumulate flow sizes
        flow_sizes = [f for (f, pl) in sources]

        for n in range(1, total_allocations+1):
            print('*** %d/%d samples'%(n, total_allocations))
            #Start global crono
            start_time = time.time()
            
            # Call sampleCongestionProbability(samples=n)
            pcs = []
            iterations = 10
            for i in range(iterations):
                pc = self.sampledCongestionProbability(graph, flow_paths, flow_sizes, n_samples=n)
                pcs.append(pc)

            # Stop crono
            duration = (time.time() - start_time)/iterations

            # Extract mean and std
            pcs = np.asarray(pcs)
            pcs_mean = float(pcs.mean())
            pcs_std = float(pcs.std())

            # Log a bit
            print("    Obtained Pc: %.3f"%(pc))
            print("    Time taken: %f"%(duration))

            # Add results to dict
            results[n] = {'pc_mean': pcs_mean,
                          'pc_std': pcs_std,
                          'duration': duration}

        return results
            

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
                    
                    if cap < 0:
                        congestion_found = True
                        # Stop checking that path in that allocation
                        break
                        
                if congestion_found:
                    congestion_samples += 1
                    # Stop checking that allocation
                    break
                
        return congestion_samples/float(total_samples)

    @staticmethod
    def random_product(*args, **kwds):
        "Random selection from itertools.product(*args, **kwds)"
        pools = map(tuple, args) * kwds.get('repeat', 1)
        return tuple(random.choice(pool) for pool in pools)

    def sampledCongestionProbability(self, all_dag, flow_paths, flow_sizes, n_samples):
        """
        In this case, path_capacities is a list of lists, representing possible flow path/s 
        min available capacities : [[c1, c2], [c2]...]
        and n is a list of flow sizes: [s1, s2, ...]

        Flow to paths bidings are given by the lists indexes.
        
        Returns estimated congestion probability.
        """
        # Choose n_samples
        #samples = []
        #action = [samples.append(self.random_product(*flow_paths)) for i in range(n_samples)]
        all_samples = list(it.product(*flow_paths))
        random.shuffle(all_samples)
        samples = all_samples[:n_samples]

        total_samples = len(samples)
        congestion_samples = 0
        
        for sample in samples:
            # Create copy of all_dag
            adag_c = all_dag.copy()
            
            # Iterate alloc. For each path i in alloc:
            for index, path in enumerate(sample):
                # Flag variable to break iteration 
                congestion_found = False
                
                # Subtract size of flow i in all_dag
                for (x, y) in zip(path[:-1], path[1:]):
                    cap = adag_c[x][y]['capacity']
                    cap -= flow_sizes[index]
                    adag_c[x][y]['capacity'] = cap
                    
                    if cap < 0:
                        congestion_found = True
                        # Stop checking that path in that allocation
                        break
                        
                if congestion_found:
                    congestion_samples += 1
                    # Stop checking that allocation
                    break
                
        return congestion_samples/float(total_samples)


    def makePlot(self, results, what='all'):
        """
        """
        # Retrieve exact pc and pop it from results
        exactPc = results['exact']
        results.pop('exact')
        print("*** Exact Pc: %.5f"%exactPc)
        
        # Extract x axis
        ss = results.keys()
        ss = sorted(ss)

        # Collect durations, avgs and stds
        avgs = []
        stds = []
        durations = []
        for s in ss:
            avgs.append(results[s]['pc_mean'])
            stds.append(results[s]['pc_std'])
            durations.append(results[s]['duration'])
            
        # Compute percents
        ss = [s/float(len(ss))*100 for s in ss]
            
        # Compute errors
        errors = [abs(a-exactPc) for a in avgs]

        # Start figure
        fig = plt.figure(1)

        if what=='all':
            ##### Plot averages first
            # Calculate ratios
            import ipdb; ipdb.set_trace()

            # Configure plot
            ax1 = fig.add_subplot(2,1,1)  
            ax1.plot(ss, avgs, 'b.', label='Average Pc')
            ax1.axhline(y=exactPc, xmin=0, xmax=100, color='r', label='exact Pc')
            ax1.set_title("Estimated Pc", fontsize=20)
            ax1.set_ylabel("Average Pc", fontsize=16)
            ax1.set_ylim(0.5, 1)
            ax1.grid(True)
            ax2 = ax1.twinx()
            ax2.plot(ss, stds, 'g-', label='Std')
            ax2.set_ylabel("Standard deviation", fontsize=16)
            #ax2.set_ylim(0,1)
            h1, l1 = ax1.get_legend_handles_labels()
            h2, l2 = ax2.get_legend_handles_labels()
            ax1.legend(h1+h2, l1+l2, loc='upper right')

            #### Plot error
            ax = fig.add_subplot(2,1,2)
            ax.plot(ss, errors, '.')
            ax.set_title('Estimation error', fontsize=20)
            ax.set_ylabel("Error", fontsize=16)
            ax.set_ylim(0, 0.2)
            ax.grid(True)

            ##### Plot total time to compute minPc
            # Calculate times
            #ax = fig.add_subplot(3,1,3)
            #ax.plot(ss, durations, '.')
            #ax.set_title('Computation time', fontsize=20)
            #ax.set_ylabel("Time (s)")
            #ax.grid(True)
            
            
            #### Final plot details
            #        import ipdb; ipdb.set_trace()
            #fig.subplots_adjust(bottom=0.10, left=0.12, right=0.90, top=0.95, wspace=0.2, hspace=0.31)
            plt.xlabel("% of allocation samples", fontsize=16)
            plt.show()

        else:
            if what not in ['average', 'error', 'duration']:
                print("*** ERROR: what parameter must be: average|errors|duration")
            else:
                if what == 'average':
                    # Configure plot
                    ax = fig.add_subplot(1,1,1)  
                    ax.plot(ss, avgs, '.')
                    ax.plot((0, exactPc), (100, exactPc), 'r-')
                    ax.set_title("Average Pc per", fontsize=20)
                    ax.set_ylabel("Average Pc", fontsize=16)
                    ax.set_ylim(0,1)
                    ax.grid(True)

                    #### Final plot details
                    #        import ipdb; ipdb.set_trace()
                    #fig.subplots_adjust(bottom=0.10, left=0.12, right=0.90, top=0.95, wspace=0.2, hspace=0.31)
                    plt.xlabel("% of DAG samples", fontsize=16)
                    plt.show()

                elif what == 'errors':     
                    #### Plot error
                    ax = fig.add_subplot(1,1,1)
                    ax.plot(ss, errors, '.')
                    ax.set_title('Calculation Pc error', fontsize=20)
                    ax.set_ylabel("Error")
                    ax.set_ylim(0,0.2)
                    ax.grid(True)

                    #### Final plot details
                    #        import ipdb; ipdb.set_trace()
                    fig.subplots_adjust(bottom=0.10, left=0.12, right=0.90, top=0.95, wspace=0.2, hspace=0.31)
                    plt.xlabel("% of DAG samples", fontsize=16)
                    plt.show()

                else:
                    ##### Plot total time to compute minPc
                    # Calculate times
                    ax = fig.add_subplot(1,1,1)
                    ax.plot(ss, durations, '.')
                    ax.set_title('Computation time', fontsize=20)
                    ax.set_ylabel("Time (s)", fontsize=16)
                    ax.grid(True)
                    
                    #### Final plot details
                    #        import ipdb; ipdb.set_trace()
                    #fig.subplots_adjust(bottom=0.10, left=0.12, right=0.90, top=0.95, wspace=0.2, hspace=0.31)
                    plt.xlabel("% of allocation samples", fontsize=16)
                    plt.show()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--nodes", type=int, help="Number of nodes in the network")
    parser.add_argument("-p", "--probability", type=float, help="Edge probability")
    parser.add_argument("--plot", type=str, help="Give results file to plot")
    parser.add_argument("--what", type=str, help="What to plot: ratios|gtimes|ptimes")
    args = parser.parse_args()

    # Parse input parameters
    if args.nodes and args.probability:
        n = args.nodes
        p = args.probability

        # Create object
        evaluation = Evaluation(n, p)

        # Run experiment
        results = evaluation.run()
        
        # Stop to check first
        import ipdb; ipdb.set_trace()
        
        # Marshal results
        id = random.randint(1, 1000)
        evaluation.saveResults(results, n, p, id)

        # Plot results
        evaluation.makePlot(results)

    else:
        if not args.plot:
            print "--plot filename must be present!"
            exit
        else:
            if not args.what:
                what = 'all'
            else:
                what = args.what

            filename = args.plot
            # Get n and p from filename
            n = int(filename.split('_')[2])
            p1 = filename.split('_')[3]
            p2 = filename.split('_')[4]
            pstr = p1+'.'+p2
            p = float(pstr)
            
            # Create object
            evaluation = Evaluation(n, p)
            
            # Load results
            results = evaluation.loadResults(args.plot)
            
            # Plot them
            evaluation.makePlot(results, what)
                    


        
