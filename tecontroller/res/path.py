"""
This module implements the Path object class
"""

import ipaddress as ip

class Path(object):
    """Implements the abstract path object representing the between nodes
    in a (general) network.

    """
    def __init__(self, route=[], edges={}):

        self.route = route #Ordered list of nodes in the path. Nodes
                           #can be prefixes or routers.
        self.index = 0
        self.edges = edges #Dictionary containing information about the
                           #edges of the path: {(x, y):{'bw':1, 'weight':4},
                           #                    (y, u):{...}
        self.src = self._setSrc(route)
        self.dst = self._setDst(route)


    def __setitem__(self, key, value):
        if key not in ['route','edges']:
            raise KeyError
        elif key == 'route':
            self.route = value
            self.src = self._setSrc(value)
            self.dst = self._setDst(value)
        else: #'edges'
            self.edges = value
            
    def __getitem__(self, key):
        if key not in ['src','dst','route','edges']:
            raise KeyError
        else:
            return self.__getattribute__(key)

    def _setSrc(self, route):
        if route != []:
            return route[0]
        else:
            return None


    def _setDst(self, route):
        if route != []:
            return route[-1]
        else:
            return None

    def __eq__(self, other):
         return (isinstance(other, self.__class__) and self.__dict__
                 == other.__dict__)
                           
    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        S = "Path(%s)"
        return S%(self.route)
    
    def __str__(self):
        S = "(%s -> %s): "
        return S%(self.src, self.dst)+str(self.route)


    def coincidentPaths(self, other):
        """Checks if two paths coincede in some edge along their
        routes. Returns true if they do.

        """
        result = [True for ((a,b), data) in self.iter_edges() if
                   (a,b) in other.getEdges().keys() or (b,a) in
                   other.getEdges().keys()]
        return result != []


    def getCoincidentEdges(self, other):
        """Given two paths, returns the edge information of those edges
        present in both paths. Returns empty dictionary otherwise.

        """
        result = {(a,b): data for ((a, b), data) in self.iter_edges() if
                   (a,b) in other.getEdges().keys() or (b,a) in
                   other.getEdges().keys()}
        return result
                

    def getEdgeInfo(self, x, y):
        """Given edge (x,y), searches (x,y) or (y,x) in path and returns edge
        information.

        """
        a = [data for edge, data in self.iter_edges() if (x,y) == edge
             or (y,x) == edge]
        if a != []:
            return a[0]
        else:
            return {}

    def iter_nodes(self):
        for index in range(len(self.route)):
            yield self.route[index]

    def iter_edges(self):
        for (edge, data) in self.edges.iteritems():
            yield (edge, data)


class IPNetPath(Path):
    def __init__(self, route=[], edges={}):
        super(IPNetPath, self).__init__(route, edges)          
            
    def getMinBw(self):
        """Returns the lowest bandwidth found on links of the path
        """
        min_bw = 0
        datas = [data for (_, data) in self.iter_edges()]
        bws = [d['bw'] for d in datas] 
        return min(bws)
