"""This module implements the DatabaseHandler object, that offers
some functions that make easier to handle with the Topology DataBase
"""
from tecontroller.res import defaultconf as dconf
from fibbingnode.misc.mininetlib.ipnet import TopologyDB
import ipaddress

class DatabaseHandler(object):
    def __init__(self):
        # Read the topology info from DB_Path
        self.db = TopologyDB(db=dconf.DB_Path)

    def _db_getNameFromIP(self, x):
        """Returns the name of the host or the router given the ip of the
        router or the ip of the router's interface towards that
        subnet.
        """
        if x.find('/') == -1: # it means x is a router id
            ip_router = ipaddress.ip_address(x)
            name = [name for name, values in
                    self.db.network.iteritems() if values['type'] ==
                    'router' and
                    ipaddress.ip_address(values['routerid']) ==
                    ip_router][0]
            return name
        
        elif 'C' not in x: # it means x is an interface ip and not the
                           # weird C_0
            ip_iface = ipaddress.ip_interface(x)
            for name, values in self.db.network.iteritems():
                if values['type'] != 'router':
                    for key, val in values.iteritems():    
                        if isinstance(val, dict):
                            ip_iface2 = ipaddress.ip_interface(val['ip'])
                            if ip_iface.network == ip_iface2.network:
                                return name

    def _db_getIPFromHostName(self, hostname):
        """Given the hostname of the host/host subnet, it returns the ip address
        of the interface in the hosts side. It is obtained from TopoDB

        It can also be called with a router name i.e: 'r1'
        """
        values = self.db.network[hostname]
        if values['type'] == 'router':
            return ipaddress.ip_address(values['routerid']).compressed
        else:
            ip = [ipaddress.ip_interface(v['ip']) for v in
                  values.values() if isinstance(v, dict)][0]
            return ip.compressed
        
    def _db_getSubnetFromHostName(self, hostname):
        """Given the hostname of a host (e.g 's1'), returns the subnet address
        in which it is connected.
        """
        hostinfo = [values for name, values in
                    self.db.network.iteritems() if name == hostname
                    and values['type'] != 'router'][0]
        
        if hostinfo is not None:
            for key, val in hostinfo.iteritems():
                if isinstance(val, dict) and 'ip' in val.keys():
                    rname = key
                    return self.db.subnet(hostname, rname)
        else:
            raise TypeError("Routers can't")

    def _db_getConnectedRouter(self, hostname):
        """Get connected router information from hostname given its name.

        """
        hostinfo = [values for name, values in
                    self.db.network.iteritems() if name == hostname
                    and values['type'] != 'router'][0]
        
        if hostinfo is not None:
            for key, val in hostinfo.iteritems():
                if isinstance(val, dict) and 'ip' in val.keys():
                    router_name = key
                    router_id = self._db_getIPFromHostName(router_name)
                    return router_name, router_id


    def _db_getRouters(self):
        """Returns a list of name-routerid bindings: [('r1', '192.153.2.2'),
        ...]
        """
        return [(node, data['routerid']) for node, data in
                self.db.network.iteritems() if data['type'] == 'router']

    def _db_getEdge(self, x, y):
        """x and y are assumed to be strings representing the name of the
        network nodes (either routers, hosts or controllers: 'r1',
        'c1', 's1'...
        """
        return self.db.network[x][y]
    
    def _db_getAllEdges(self):
        """Returns all edge information from the network. It is used in the
        Links Monitor object.
        """
        i = 0
        edges = {}
        for node, data in self.db.network.iteritems():
            if data['type'] == 'router':
                for neighbor, ndata in data.iteritems():
                    if neighbor != 'type' and neighbor != 'routerid':
                        edgeData = self._db_getEdge(node, neighbor)
                        linkname = "L%d"%i
                        i += 1
                        edges[linkname] = {'edge': (node, neighbor),
                                           'bw': edgeData['bw']*1e6,
                                           'load': 0,
                                           'interface': edgeData['name']} 
        return edges
