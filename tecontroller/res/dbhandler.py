"""This module implements the DatabaseHandler object, that offers
some functions that make easier to handle with the Topology DataBase
"""
from tecontroller.res import defaultconf as dconf
from fibbingnode.misc.mininetlib.ipnet import TopologyDB
import ipaddress


class DatabaseHandler(TopologyDB):
    def __init__(self):
        super(DatabaseHandler, self).__init__(db=dconf.DB_Path)
        
        # Data structures that keep the hosts and routers to ip
        # bindings
        self.hosts_to_ip = {}
        self.routers_to_ip = {}

        # Fill up the dictionaries with the corresponding bindings
        self._createHost2IPBindings()
        self._createRouter2IPBindings()
        
    def _createHost2IPBindings(self):
        """Fills the dictionary self.hosts_to_ip with the corresponding
        name-ip pairs
        """
        # Collect hosts only
        hosts = [(name, data) for (name, data) in self.network.iteritems() if data['type'] == 'host']
        for (name, data) in hosts:
            # Check if it is connected to a router directly or to a switch
            # Remove the type first
            data_c = data.copy()
            data_c.pop('type')
            
            # Check if connected device is host or router
            connected = data_c.keys()[0]
            type_connected = self.network[connected]['type']
            if type_connected == 'switch':
                connected_switch = connected
            else:
                connected_switch = None

            node_ip = [v['ip'] for (k, v) in data_c.iteritems() if isinstance(v, dict)]
            if node_ip:
                node_ip = node_ip[0]
                ip_iface_host = self.getIpFromHostName(name)
                ip_iface_router = self.getSubnetFromHostName(name)
                router_name, router_id = self.getConnectedRouter(name) 
                self.hosts_to_ip[name] = {'iface_host': ip_iface_host,
                                          'iface_router': ip_iface_router,
                                          'router_name': router_name,
                                          'router_id': router_id,
                                          'switch': connected_switch}

    def _createRouter2IPBindings(self):
        """Fills the dictionary self.routers_to_ip with the corresponding
        name-ip pairs
        """
        routers = [(name, data) for (name, data) in self.network.iteritems() if data['type'] == 'router']
        for (name, data) in routers:
            self.routers_to_ip[name] = data['routerid']
            
    def getNameFromIP(self, x):
        """
        Returns the name of the host or the router given the ip of the
        router or the ip of the router's interface towards that
        subnet.
        """
        if x.find('/') == -1: # it means x is a router id
            ip_router = ipaddress.ip_address(x)
            name = [name for name, values in
                    self.network.iteritems() if values['type'] ==
                    'router' and
                    ipaddress.ip_address(values['routerid']) ==
                    ip_router][0]
            return name
        
        elif 'C' not in x: # it means x is an interface ip and not the
                           # weird C_0
            ip_iface = ipaddress.ip_interface(x)
            hosts = [(n,v) for n, v in self.network.iteritems() if v['type'] == 'host']
            for (n, v) in hosts:
                for key, val in v.iteritems():    
                    if isinstance(val, dict):
                        ip_iface2 = ipaddress.ip_interface(val['ip'])
                        if ip_iface.ip == ip_iface2.ip:
                            return n
        else:
            return None

    def getIpFromHostName(self, hostname):
        """Given the hostname of the host, it returns the ip address
        of the interface in the hosts side. It is obtained from TopoDB

        It can also be called with a router name i.e: 'r1'
        
        switches will return None.
        """
        values = self.network[hostname]
        host_type = values.get('type', None)
        if host_type == 'switch':
            return None

        elif host_type == 'router':
            return values['routerid']
        
        elif host_type == 'host':
            ip = [v['ip'] for v in values.values() if isinstance(v, dict)][0]
            return ip
        else:
            return None

        
    def getSubnetFromHostName(self, hostname):
        """Given the hostname of a host (e.g 's1'), returns the subnet address
        in which it is connected.
        """
        try:
            hostinfo = [values for name, values in
                        self.network.iteritems() if name == hostname
                        and values['type'] != 'router'][0]
        except:
            import ipdb;ipdb.set_trace()
        if hostinfo is not None:
            for key, val in hostinfo.iteritems():
                if isinstance(val, dict) and 'ip' in val.keys():
                    rname = key
                    return self.subnet(hostname, rname)
        else:
            raise TypeError("Routers can't")

        
    def isSwitch(self, hostname):
        return self.network[hostname]['type'] == 'switch'
    
        
    def getConnectedRouter(self, hostname):
        """Get connected router information from hostname given its name.
        """
        hostinfo = self.network.get(hostname, None)
        if hostinfo and hostinfo['type'] == 'host':
            for key, val in hostinfo.iteritems():
                if isinstance(val, dict) and 'ip' in val.keys():
                    if self.isSwitch(key):
                        switch_name = key
                        routers = [(n,v) for n,v in self.network.iteritems() if v['type'] == 'router']
                        get_the_one = [(n, v[switch_name]['ip']) for (n, v) in routers if switch_name in v.keys()]
                        if get_the_one != []:
                            (router_name, _) = get_the_one[0]
                            router_id = self.network[router_name]['routerid']
                    else:
                        router_name = key
                        router_id = self.network[router_name]['routerid']
                    return router_name, router_id
                
    def getRouters(self):
        """Returns a list of name-routerid bindings: [('r1', '192.153.2.2'),
        ...]
        """
        return [(node, data['routerid']) for node, data in
                self.network.iteritems() if data['type'] == 'router']

    def getEdge(self, x, y):
        """x and y are assumed to be strings representing the name of the
        network nodes (either routers, hosts or controllers: 'r1',
        'c1', 's1'...
        """
        return self.network[x][y]
    
    def getAllEdges(self):
        """Returns all edge information from the network. It is used in the
        Links Monitor custom host.
        """
        i = 0
        edges = {}
        for node, data in self.network.iteritems():
            if data['type'] == 'router':
                for neighbor, ndata in data.iteritems():
                    if neighbor != 'type' and neighbor != 'routerid':
                        edgeData = self.getEdge(node, neighbor)
                        linkname = "L%d"%i
                        i += 1
                        edges[linkname] = {'edge': (node, neighbor),
                                           'bw': edgeData['bw']*1e6,
                                           'load': 0,
                                           'interface': edgeData['name']} 
        return edges

    def getAllRouterEdges(self):
        """
        Returns all information about router to router edges.
        It is used in the LinksMonitorThread.
        """
        edges = {}
        for node, data in self.network.iteritems():
            if data['type'] == 'router':
                for neighbor, ndata in data.iteritems():
                    if isinstance(ndata, dict) and self.network[neighbor].get('type', None) == 'router':
                        x = self.routerid(node)
                        y = self.routerid(neighbor)
                        edges[(x, y)] = {
                            'bw': ndata['bw']*1e6,
                            'capacity': ndata['bw']*1e6,
                            'interface': ndata['name']
                            }
        return edges


    def getRouterControlIp(self, r):
        """Given a router id, it returns the control-network IP for that
        router. If control network can't be found, return None"""
        router_name = [n for n, data in self.network.iteritems() if
                       data['type'] == 'router' and data['routerid'] == r]
        if router_name != []:
            router_name = router_name[0]
            # Get the ip of that router pointing to s1 switch: control
            # network.
            if 's1' in self.network[router_name].keys():
                ip_iface_str = self.network[router_name]['s1']['ip']
                ip = ipaddress.ip_interface(ip_iface_str).ip.compressed
                return ip
            else:
                return None
        else:
            return None
