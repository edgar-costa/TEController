import ipaddress as ip
import networkx as nx
from tecontroller.res.flow import Flow
from tecontroller.loadbalancer.simplepathlb import SimplePathLB
from tecontroller.loadbalancer.ecmplb import ECMPLB
from tecontroller.loadbalancer.lbcontroller import LBController

import time

# Start LBC controller
# lbc = LBController()

lbc = SimplePathLB()
#lbc = ECMPLB()

# Get router addresses
r1 = lbc.db.routerid('r1')
r2 = lbc.db.routerid('r2')
r3 = lbc.db.routerid('r3')

#r4 = lbc.db.routerid('r4')

# Get subnet addresses
d1 = lbc.db.hosts_to_ip['d1']['iface_host']
d2 = lbc.db.hosts_to_ip['d2']['iface_host']
d3 = lbc.db.hosts_to_ip['d3']['iface_host']
t1 = lbc.db.hosts_to_ip['t1']['iface_host']
t2 = lbc.db.hosts_to_ip['t2']['iface_host']
t3 = lbc.db.hosts_to_ip['t3']['iface_host']
#x1 = lbc.hosts_to_ip['x1']['iface_host']
#x2 = lbc.hosts_to_ip['x2']['iface_host']
#x3 = lbc.hosts_to_ip['x3']['iface_host']
#y1 = lbc.hosts_to_ip['y1']['iface_host']
#y2 = lbc.hosts_to_ip['y2']['iface_host']
#y3 = lbc.hosts_to_ip['y3']['iface_host']
s1 = lbc.db.hosts_to_ip['s1']['iface_host']
s2 = lbc.db.hosts_to_ip['s2']['iface_host']


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

