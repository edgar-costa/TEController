import networkx as nx
from tecontroller.res.flow import Flow
from tecontroller.loadbalancer.simplepathlb import SimplePathLB
from tecontroller.loadbalancer.ecmplb import ECMPLB
from tecontroller.loadbalancer.lbcontroller import LBController

import time

# Start LBC controller
#lbc = LBController()
lbc = SimplePathLB()
#lbc = ECMPLB()

# Get router addresses
r1 = lbc.db.routerid('r1')
r2 = lbc.db.routerid('r2')
r3 = lbc.db.routerid('r3')
r4 = lbc.db.routerid('r4')

# Get subnet addresses
s1 = lbc.getSubnetFromHostName('s1')
s2 = lbc.getSubnetFromHostName('s2')
s3 = lbc.getSubnetFromHostName('s3')
s4 = lbc.getSubnetFromHostName('s4')
s5 = lbc.getSubnetFromHostName('s5')

d1 = lbc.getSubnetFromHostName('d1')
d2 = lbc.getSubnetFromHostName('d2')
d3 = lbc.getSubnetFromHostName('d3')
d4 = lbc.getSubnetFromHostName('d4')

"""
## DO FOR ALL TESTS ##############################################################
# Get the event from the queue
event = lbc.eventQueue.get()
print "Event Collected!"

# Retrieve flow
flow = event['data']

# Get first the destination subnet
src_subnet = flow['src'].network.compressed
dst_subnet = flow['dst'].network.compressed

# Get source hostname
src_hostname = lbc._db_getNameFromIP(flow['src'].compressed) 
dst_hostname = lbc._db_getNameFromIP(flow['dst'].compressed) 


## SIMPLE PATH TESTS ##############################################################

# Calculate current active path/s from source to destination
apaths = lbc.getActivePaths(src_subnet, dst_subnet)

# Print them
print lbc.toRouterNames(apaths)




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

# Now let's change the flow from path again
(x,y) = (default_path[0], default_path[1])
ng2 = lbc.getNetworkWithoutEdge(ng, x, y)
(x,y) = (path2[0], path2[1])
ng2 = lbc.getNetworkWithoutEdge(ng2, x, y)

# Calculate next default dijkstra path frmo src to dst
path3 = nx.dijkstra_path(ng2, src_router_id, dst_subnet.compressed)

# Enforce it with FIBBING
lbc.sbmanager.simple_path_requirement(dst_subnet.compressed, [r for r in path3 if
                                                   r in lbc.routers_to_ip.values()])

## Remove LSA test ########################################################################

# Remove the last hop (destination prefix)
default_path = default_path[:-1]
path2 = path2[:-1]

# Create the DiGraph (DAG)
branch1 = [(s, d) for s, d in zip(default_path[:-1], default_path[1:])]
branch2 = [(s, d) for s, d in zip(path2[:-1], path2[1:])]
dag = nx.DiGraph(branch1+branch2)

lbc.sbmanager.fwd_dags[dst_subnet.compressed] = dag
lbc.sbmanager.refresh_lsas()

# Get lsa for that destination
lsa = lbc.getLiesFromPrefix(dst_subnet)

# Remove corresponding lsa
lbc.sbmanager.remove_lsa(lsa)



## ECMP TESTS ####################################################################
# Get path 1 (default)
path1 = nx.dijkstra_path(ng, src_router_id, dst_subnet.compressed)
path1 = path1[:-1]

# Get path 2 
(x,y) = (path1[0], path1[1])
ng2 = lbc.getNetworkWithoutEdge(ng, x, y)

# Calculate next default dijkstra path frmo src to dst 
path2 = nx.dijkstra_path(ng2, src_router_id, dst_subnet.compressed)
path2 = path2[:-1]

# Create branches of the DAG
branch1 = [(s, d) for s, d in zip(path1[:-1], path1[1:])]                               
branch2 = [(s, d) for s, d in zip(path2[:-1], path2[1:])]                                             

# Create DAG
dag = nx.DiGraph(branch1+branch2)

# Insert it in the network
lbc.sbmanager.fwd_dags[dst_subnet.compressed] = dag
lbc.sbmanager.refresh_lsas()



"""

