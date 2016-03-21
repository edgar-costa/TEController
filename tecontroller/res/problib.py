"""Module that implements the functions to calculate the congestion
probabilities when activating ECMP in a routers of a network. 
"""

def getPathProbability(dag, path):
    """Given a DAG and a path defined as a succession of nodes in the
    DAG, it returns the probability of a single flow to be allocated
    in that path.
    """
    probability = 1
    for node in path:
        children = len(dag[node])
        probability *= 1/children
    return probability

def getAllPathsLimDAG(dag, start, end, k, path=[]):
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

def getMinCapacity(dag, path):
    """
    Iterate dag through edges of the path and return the 
    minimum observed available capacity
    """
    caps = [dag[u][v]['capacity'] for u, v in zip(path[:-1], path[1:])]
    return min(caps)

def flowCongestionProbability(dag, ingress_router, egress_router, flow_size):
    """We assume DAG edges incorporate the available capacities:
    dag[x][y] is a dictionary with a 'capacity' key.
    """
    all_paths = getAllPathsLimDAG(dag, ingress_router, egress_router, 0)
    paths_congestion = [path for path in all_paths if getMinCapacity(dag, path) < flow_size]
    congestion_probability = 0
    for path in paths_congestion:
        congestion_probability += getPathProbability(dag, path)
    return congestion_probability
