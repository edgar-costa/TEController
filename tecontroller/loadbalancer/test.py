import networkx as nx
from tecontroller.res.path import IPNetPath as Pth
from tecontroller.res.flow import Flow
from tecontroller.loadbalancer.lbcontroller import LBController

lbc = LBController()
ng = lbc.network_graph

s1 = lbc._db_getIPFromHostName('s1')
d1 = lbc._db_getIPFromHostName('d1')
flow = Flow(src=s1, dst=d1, size='500K')
path = lbc.getDefaultDijkstraPath(flow)
lbc.getMinCapacity(path)
if lbc.canAllocateFlow(path, flow):
    lbc.addFlowToPath(path, flow)
