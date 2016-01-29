"""
This module implements the Path object class
"""

import ipaddress as ip


class Path(object):
    """Implements a path object representing the between prefixes in a
    network

    """
    def __init__(self, src=None, dst=None, route=[], edges={}):
        self.src=src
        self.dst=dst
        self.route = route #Ordered list of nodes in the path. Nodes
                           #can be prefixes or routers.
        self.index = 0
        self.edges = edges #Dictionary containing information about the
                           #edges of the path: {(x, y):{'bw':1, 'weight':4},
                           #                    (y, u):{...}

    def __repr__(self):
        S = "(%s -> %s)"
        return S%(self.src, self.dst)#+str(self.route)

    def getRoute(self):
        return self.route
    
    def setRoute(self, route):
        self.route = route
        if nodes:
            self.src = route[0]
            self.dst = route[-1]
        else:
            self.src = None
            self.dst = None
            
    def getEdges(self):
        return self.edges

    def iter_nodes(self):
        for index in range(len(self.route)):
            yield self.route[index]

    def iter_edges(self):
        for (edge, data) in self.edges.iteritems():
            yield (edge, data)

    def getMinBw(self):
        """Returns the lowest bandwidth found on links of the path
        """
        min_bw = 0
        datas = [data for (_, data) in self.iter_edges()]
        bws = [d['bw'] for d in datas] 
        return min(bws)
