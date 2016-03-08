import ipaddress as ip
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

d1 = lbc.hosts_to_ip['d1']['iface_host']
d2 = lbc.hosts_to_ip['d2']['iface_host']
d3 = lbc.hosts_to_ip['d3']['iface_host']
t1 = lbc.hosts_to_ip['t1']['iface_host']
t2 = lbc.hosts_to_ip['t2']['iface_host']
t3 = lbc.hosts_to_ip['t3']['iface_host']
x1 = lbc.hosts_to_ip['x1']['iface_host']
x2 = lbc.hosts_to_ip['x2']['iface_host']
x3 = lbc.hosts_to_ip['x3']['iface_host']
y1 = lbc.hosts_to_ip['y1']['iface_host']
y2 = lbc.hosts_to_ip['y2']['iface_host']
y3 = lbc.hosts_to_ip['y3']['iface_host']


"""
# LONGER PREFIX TEST ####################################
# Create traffic to x1 first (tgcommander)

# Get the event from the queue
event = lbc.eventQueue.get()
print "Event Collected!"

# Retrieve flow
flow = event['data']

# Get current advertised prefix for flow
current_prefix = lbc.getCurrentOSPFPrefix(flow['dst'].compressed)

# Defaut path (hardcoded) as if it was fibbed
# we make it collide with flow to x2
path_list = [[r1,r4,r3]]

# Add it in the allocation table
lbc.flow_allocation[current_prefix.compressed] = {}
lbc.flow_allocation[current_prefix.compressed][flow] = path_list

# Test destination
x2_dd = lbc.getCurrentOSPFPrefix(x2)
x2_ip = ip.ip_interface(x2).ip
new_path_list = [[r1,r2,r3]]

# Create DAG for x2
dag = nx.DiGraph()
dag.add_edges_from([(r1,r2),(r2,r3),(r4,r3)])

# Get the longer prefix
newLongerPrefix = lbc.getNextNonCollidingPrefix(x2_ip, x2_dd, [[r1,r2,r3]])
if newLongerPrefix == None:
    print "Error"


# Fib it
lbc.sbmanager.add_dag_requirement(newLongerPrefix.compressed, dag)

# Then start new flow towards x2 to see if it worked


##############################################




dst_iface = d1
dst_iface = ip.ip_interface(dst_iface)
dst_ip = dst_iface.ip
dst_nw = dst_iface.network
current_nw_prefix = lbc.getCurrentOSPFPrefix(dst_iface)

# Add some ongoing flows
f1 = Flow(src=s1, dst=d1)
f2 = Flow(src=s3, dst=d1)

lbc.flow_allocation[dst_nw.compressed]={f1:[[r1,r4,r3]], f2:[[r2,r3]]}

dst_ip = ip.ip_address('192.168.255.221')






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

