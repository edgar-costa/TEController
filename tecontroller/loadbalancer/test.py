import networkx as nx
from tecontroller.res.path import IPNetPath as Pth
from tecontroller.res.flow import Flow
from tecontroller.loadbalancer.lbcontroller import LBController
import time

# Start LBC controller
lbc = LBController()
ng = lbc.network_graph

"""
# Get the event from the queue
event = lbc.eventQueue.get()
print "Event Collected!"

# Retrieve flow
flow = event['data']

# Get router addresses
r1 = lbc.db.routerid('r1')
r2 = lbc.db.routerid('r2')
r3 = lbc.db.routerid('r3')

# Get first the destination subnet
dst_subnet = flow['dst'].network

# Get source hostname
src_hostname = lbc._db_getNameFromIP(flow['src'].compressed) 

# Get source attached router
(src_router_name, src_router_id) = lbc._db_getConnectedRouter(src_hostname)

# Calculate default dijkstra path from src to dst
default_path = nx.dijkstra_path(ng, src_router_id, dst_subnet.compressed)

# Remove edge from path
(x,y) = (default_path[0], default_path[1])
ng2 = lbc.getNetworkWithoutEdge(ng, x,y)

# Calculate next default dijkstra path frmo src to dst
path2 = nx.dijkstra_path(ng2, src_router_id, dst_subnet.compressed)

# Enforce it with FIBBING
lbc.sbmanager.simple_path_requirement(dst_subnet.compressed, [r for r in path2 if
                                                   r in lbc.routers_to_ip.values()])
# Get lsa for that destination
lsa = lbc.getLiesFromPrefix(dst_subnet)

# Remove corresponding lsa
lbc.sbmanager.remove_lsa(lsa)

"""

