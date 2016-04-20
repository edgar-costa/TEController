import networkx as nx
import random
import itertools as it

def getMergedDag(start, end, path_list):
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
                ## Eliminate loop edges at random
                # Get simple cycles
                simple_cycles = [c for c in nx.simple_cycles(composedDag)]
                
                ## Eliminate loops
                for cycle in simple_cycles:
                        # Remove cycle edge at random
                        cycle_edges = zip(cycle[:-1], cycle[1:])
                        random.shuffle(cycle_edges)
                        (x, y) = cycle_edges[0]
                        if (x,y) in composedDag.edges():
                                composedDag.remove_edge(x, y)

	# Compute all paths on randomDag (to eliminate dummy paths)
	all_final_paths = getAllPathsLim(composedDag, start, end, k=0)

	pathsDags = []
	for path in all_final_paths:
		tmp_dag = nx.DiGraph()
		tmp_dag.add_edges_from(zip(path[:-1], path[1:]))
		pathsDags.append(tmp_dag)
	
	finalMergedDag = nx.compose_all(pathsDags)
	return finalMergedDag

def getRandomDag(graph, start, end):
	"""
	Given a network graph, and start and end nodes, computes
	 a random DAG from start towards end nodes. 
	"""
	start_time = time.time()

	## Calculate firts all paths from start to end
	all_paths = getAllPathsLim(graph, start, end, k=0)

	## Chose a random subset of them
	n_paths_chosen = random.randint(1, len(all_paths))
	# Randomly shuffle list of all paths
	random.shuffle(all_paths)
	chosen_paths =  all_paths[:n_paths_chosen]

	# Compute merged DAG for all randomly chosen paths
	finalRandomDag = getMergedDag(start, end, chosen_paths)
	return finalRandomDag	


def getRandomDag(graph, start, end):
	# Save nodes for which the choice of a random 
	# subset of its edges was done
	traversed_nodes = set()

	# Save edges that can't be chosen anymore:
	#  1) Edges that were not randomly chosen (and opposite edge)
	#  2) All 
	forbidden_edges = set()





def getRandomSinglePathDag(graph, start, end):
	"""
	Given a network graph, and start and end nodes, returns 
	a DAG with a chosen random single path from start to end nodes. 
	"""

	## Calculate firts all paths from start to end
	all_paths = getAllPathsLim(graph, start, end, k=0)

	## Chose a random subset of them
	random_index = random.randint(0, len(all_paths)-1)

	# Randomly shuffle list of all paths
	chosen_path =  all_paths[random_index]

	# Convert path into DAG
	finalDag = nx.DiGraph()
	finalDag.add_edges_from(zip(chosen_path[:-1], chosen_path[1:]))
	
	return finalDag	

def getAllPossibleSinglePathDags(graph, start, end):
	## Calculate firts all paths from start to end
	all_paths = getAllPathsLim(graph, start, end, k=0)

	all_dags = []
	for path in all_paths:
		# Convert path into DAG
		tmpDag = nx.DiGraph()
		tmpDag.add_edges_from(zip(path[:-1], path[1:]))
		all_dags.append(tmpDag)

	return all_dags

def getAllPossibleDags(graph, start, end):
        """
	Given a network graph, and start and end nodes, computes
	a random DAG from start towards end nodes. 
	"""
	## Calculate firts all paths from start to end
	all_paths = getAllPathsLim(graph, start, end, k=0)

        # Calculate all combinations of possible paths.
   	all_path_subsets = []
   	action = [all_path_subsets.append(c) for i in range(1, len(all_paths)+1) for c in list(it.combinations(all_paths, i))]

   	# Compute merge of dags
   	allRandomDags = []
   	for subset in all_path_subsets:
   		mergedDag = getMergedDag(start, end, subset)
   		allRandomDags.append(mergedDag)

   	# Check for duplicates
   	uniqueDags = []
	for rdag in allRandomDags:
   		# Search first if seen in uniqueDags
   		seenUD = [e for e in uniqueDags if rdag.edges() == e[0]]
   		if seenUD == []:
   			# not seen before
   			uniqueDags += [(rdag.edges(), 1, rdag)]
   		else:
   			(ude, fq, ud) = seenUD[0]
   			uniqueDags.remove(seenUD[0])
   			uniqueDags += [(ude, fq+1, ud)]

   	#Collect unique dags and return them
   	allPossibleDags = [c for (a,b,c) in uniqueDags]

   	return allPossibleDags

def getAllPossibleMultiplePathDags(graph, start, end):
	"""
	Given a network graph, and start and end nodes, computes
	a random DAG from start towards end nodes. 
	"""
	## Calculate firts all paths from start to end
	all_paths = getAllPathsLim(graph, start, end, k=0)

        # Calculate all combinations of possible paths.
   	all_path_subsets = []
   	action = [all_path_subsets.append(c) for i in range(2, len(all_paths)+1) for c in list(it.combinations(all_paths, i))]

   	# Compute merge of dags
   	allRandomDags = []
   	for subset in all_path_subsets:
   		mergedDag = getMergedDag(start, end, subset)
   		allRandomDags.append(mergedDag)

   	# Check for duplicates
   	uniqueDags = []
	for rdag in allRandomDags:
   		# Search first if seen in uniqueDags
   		seenUD = [e for e in uniqueDags if rdag.edges() == e[0]]
   		if seenUD == []:
   			# not seen before
   			uniqueDags += [(rdag.edges(), 1, rdag)]
   		else:
   
   			(ude, fq, ud) = seenUD[0]
   			uniqueDags.remove(seenUD[0])
   			uniqueDags += [(ude, fq+1, ud)]

   	#Collect unique dags and return them
   	allPossibleDags = [c for (a,b,c) in uniqueDags]

   	return allPossibleDags

def getAllPathsLim(graph, start, end, k, path=[]):
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
        
    if not start in graph:
        return []

    paths = []
    for node in graph[start]:
        if node not in path: # Ommiting loops here
            if k == 0:
                # If we do not want any length limit
                newpaths = getAllPathsLim(graph, node, end, k, path=path)
                for newpath in newpaths:
                    paths.append(newpath)

            elif len(path) < k+1:
                newpaths = getAllPathsLim(graph, node, end, k, path=path)
                for newpath in newpaths:
                    paths.append(newpath)
    return paths


# ## TESTS #####################################

# # Create sample graph
# graph1 = nx.DiGraph()
# edges1 = [('A','B'),('B','A'),
# 	('A','F'),('F','A'),
# 	('A','D'),('D','A'),
# 	('B','F'),('F','B'),
# 	('F','E'),('E','F'),
# 	('E','D'),('D','E'),
# 	('D','C'),('C','D'),
# 	('C','A'),('A','C'),
# 	('C','B'),('B','C')]
# graph1.add_edges_from(edges1)


# graph2 = nx.DiGraph()
# edges2 = [('A','B'),('B','A'),
# 	('A','C'),('C','A'),
# 	('B','C'),('C','B'),
# 	('A','D'),('D','A'),
# 	('D','C'),('C','D')]

# graph2.add_edges_from(edges2)

# #randomDags = []
# #for i in range(10):
# 	#randomDag = getRandomDAG(graph, 'A', 'E')
# #	randomDag = getRandomSinglePathDAG(graph, 'A', 'E')
# #	print randomDag.edges()

# apd = getAllPossibleDags(graph2, 'A', 'C')
# import ipdb; ipdb.set_trace()
