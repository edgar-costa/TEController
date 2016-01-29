"""
This module implements the Path object class
"""

import ipaddress as ip


class Path(object):
    """Implements a path object representing the between prefixes in a
    network

    """
    def __init__(self, nodes=[], edges={}):
        self.nodes = nodes #Ordered list of nodes in the path. Nodes can
                           #be prefixes or routers.
        self.index = 0
        self.edges = edges #Dictionary containing information about the
                           #edges of the path: {(x, y):{'bw':1, 'weight':4},
                           #                    (y, u):{...}

    def __repr__(self):
        return str(self.nodes)

    def getNodes(self):
        return self.nodes

    def getEdges(self):
        return self.edges

    def iter_nodes(self):
        for index in range(len(self.nodes)):
            yield self.nodes[index]

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
