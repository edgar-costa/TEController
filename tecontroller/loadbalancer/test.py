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
dst_subnet = flow['dst'].network.compressed

# Get source hostname
src_hostname = lbc._db_getNameFromIP(flow['src'].compressed) 

# Get source attached router
(src_router_name, src_router_id) = lbc._db_getConnectedRouter(src_hostname)

# Calculate default dijkstra path from src to dst
default_path = nx.dijkstra_path(ng, src_router_id, dst_subnet)

# Remove edge from path
(x,y) = (default_path[0], default_path[1])
ng2 = lbc.getNetworkWithoutEdge(ng, x,y)

# Calculate next default dijkstra path frmo src to dst
path2 = nx.dijkstra_path(ng2, src_router_id, dst_subnet)

# Enforce it with FIBBING
lbc.sbmanager.simple_path_requirement(dst_subnet, [r for r in path2 if
                                                   r in lbc.routers_to_ip.values()])

"""
#s1 = lbc._db_getIPFromHostName('s1')
#d1 = lbc._db_getIPFromHostName('d1')
#flow = Flow(src=s1, dst=d1, size='500K')
#path = lbc.getDefaultDijkstraPath(flow)
#lbc.getMinCapacity(path)
#if lbc.canAllocateFlow(path, flow):
#    lbc.addFlowToPath(path, flow)


