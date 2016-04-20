import argparse

from fibbingnode import CFG

import fibbingnode.misc.mininetlib as _lib
from fibbingnode.misc.mininetlib.cli import FibbingCLI
from fibbingnode.misc.mininetlib.ipnet import IPNet, TopologyDB
from fibbingnode.misc.mininetlib.iptopo import IPTopo

from fibbingnode.algorithms.southbound_interface import SouthboundManager
from fibbingnode.algorithms.ospf_simple import OSPFSimple

from mininet.util import custom
from mininet.link import TCIntf

from tecontroller.res.mycustomhost import MyCustomHost
from tecontroller.res.mycustomrouter import MyCustomRouter

from tecontroller.trafficgenerator.trafficgenerator import TrafficGenerator
from tecontroller.res import defaultconf as dconf

import networkx as nx
import signal
import sys

C1_cfg = '/tmp/c1.cfg'

C1 = 'c1' #fibbing controller
TG = dconf.TG_Hostname #traffic generator
LBC = dconf.LBC_Hostname #Load Balancing controller

R1 = 'r1'
R2 = 'r2'
R3 = 'r3'
R4 = 'r4'
R5 = 'r5'
R6 = 'r6'
R7 = 'r7'

H10 = 'h10'
H11 = 'h11'
H12 = 'h12'

H20 = 'h20'
H21 = 'h21'
H22 = 'h22'

H30 = 'h30'
H31 = 'h31'
H32 = 'h32'
H33 = 'h33'
H34 = 'h34'

H40 = 'h40'
H41 = 'h41'
H42 = 'h42'

H50 = 'h50'
H60 = 'h60'
H70 = 'h70'

M1 = 'm1'

BW = 1  # Absurdly low bandwidth for easy congestion (in Mb)

class Lab2Topo(IPTopo):
    def build(self, testfile, pcalgorithm, *args, **kwargs):
        """
         h2's        h3's
            \        /
            r2------r3
             | _____/|  
           10|/      |
            r1------r4---[TEC,TG,FibC]
            /         \
          h1's        h4's
        """
        # Add routers and router-router links
        r1 = self.addRouter(R1, cls=MyCustomRouter)
        r2 = self.addRouter(R2, cls=MyCustomRouter)
        r3 = self.addRouter(R3, cls=MyCustomRouter)
        r4 = self.addRouter(R4, cls=MyCustomRouter)

        self.addLink(r1, r2, cost=10)
        self.addLink(r1, r4, cost=2)
        self.addLink(r1, r3, cost=2)
        self.addLink(r2, r3, cost=2)
        self.addLink(r3, r4, cost=5)

        # Create broadcast domains
        self.addLink(r1, self.addHost(H10)) 
        self.addLink(r1, self.addHost(H11)) 
        self.addLink(r1, self.addHost(H12)) 

        self.addLink(r2, self.addHost(H20))  
     	self.addLink(r2, self.addHost(H21))  
        self.addLink(r2, self.addHost(H22))  

        s2 = self.addSwitch('s2')
        self.addLink(r3, s2)
        self.addLink(s2, self.addHost(H30))
        self.addLink(s2, self.addHost(H31))
        self.addLink(s2, self.addHost(H32))
        self.addLink(s2, self.addHost(H33))
        self.addLink(s2, self.addHost(H34))

        self.addLink(r4, self.addHost(H40))
        self.addLink(r4, self.addHost(H41))
        self.addLink(r4, self.addHost(H42))

        # Adding Fibbing Controller
        c1 = self.addController(C1, cfg_path=C1_cfg)
        self.addLink(c1, r4, cost=999)

        # Adding Traffic Generator Host
        c2 = self.addHost(TG, isTrafficGenerator=True, flowfile=testfile) 
        self.addLink(c2, r4)

        # Adding Traffic Engineering Controller
        c3 = self.addHost(LBC, isLBController=True, algorithm='lab2', pcalgorithm=pcalgorithm)
        self.addLink(c3, r4)
        
        
        # Create the monitoring network
        monitorSwitch = self.addSwitch('s1')
        # connect nodes in it
        nodes_to_monitor = [r1, r2, r3, r4, c2, c3, c1]
        for n in nodes_to_monitor:
            self.addLink(monitorSwitch, n, cost=-1)


class Lab2Topo2(IPTopo):
    def build(self, testfile,pcalgorithm, *args, **kwargs):

        topo = """
            r2-------r5
           /  \     /  \
          /    \  _/    \
        r1      r4       r7
          \    /  \_    /
           \  /     \_ /
            r3--------r6
        """
        # Add routers and router-router links
        r1 = self.addRouter(R1, cls=MyCustomRouter)
        r2 = self.addRouter(R2, cls=MyCustomRouter)
        r3 = self.addRouter(R3, cls=MyCustomRouter)
        r4 = self.addRouter(R4, cls=MyCustomRouter)
        r5 = self.addRouter('r5', cls=MyCustomRouter)
        r6 = self.addRouter('r6', cls=MyCustomRouter)
        r7 = self.addRouter('r7', cls=MyCustomRouter)

        self.addLink(r1, r2)
        self.addLink(r1, r3)
        self.addLink(r2, r4)
        self.addLink(r2, r5)
        self.addLink(r3, r4)
        self.addLink(r3, r6)
        self.addLink(r4, r5)
        self.addLink(r4, r6)
        self.addLink(r5, r7)
        self.addLink(r6, r7)

        # Create broadcast domains
     	self.addLink(r1, self.addHost(S1))  
        self.addLink(r2, self.addHost(S2))  
        self.addLink(r3, self.addHost(S3))
        self.addLink(r4, self.addHost(S4))
        self.addLink(r5, self.addHost('d1'))    
        self.addLink(r6, self.addHost('t1'))
        self.addLink(r7, self.addHost('x1'))

        # Adding Fibbing Controller
        c1 = self.addController(C1, cfg_path=C1_cfg)
        self.addLink(c1, r4, cost=1000)

        # Adding Traffic Generator Host
        c2 = self.addHost(TG, isTrafficGenerator=True, flowfile=testfile) 
        self.addLink(c2, r4)

        # Adding Traffic Engineering Controller
        c3 = self.addHost(LBC, isLBController=True, algorithm='lab2', pcalgorithm=pcalgorithm)
        self.addLink(c3, r4)

        
def launch_network(testfile, pcalgorithm):
    net = IPNet(topo = Lab2Topo(testfile, pcalgorithm),
                debug =_lib.DEBUG_FLAG,
                intf = custom(TCIntf, bw = BW),
                host = MyCustomHost)
    
    TopologyDB(net = net).save(dconf.DB_Path)
    net.start()
    FibbingCLI(net)
    net.stop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-c', '--controller',
                       help='Start the controller',
                       action='store_true',
                       default=False)
    group.add_argument('-n', '--net',
                       help='Start the Mininet topology',
                       action='store_true',
                       default=True)
    parser.add_argument('-d', '--debug',
                        help='Set log levels to debug',
                        action='store_true',
                        default=False)
    parser.add_argument('-t', '--testfile',
                        help='Give path of csv file with flows for test',
                        default=dconf.Lab2_Tests+'notest.csv')
    parser.add_argument('-a', '--pcalgorithm',
                        help='Give the name of the algorithm used to compute congestion probabilities: exact|sampled|simplified',
                        default='exact')
    args = parser.parse_args()
    
    if args.debug:
        _lib.DEBUG_FLAG = True
        from mininet.log import lg
        from fibbingnode import log
        import logging
        log.setLevel(logging.DEBUG)
        lg.setLogLevel('debug')
    if args.controller:
        launch_controller()
        
    elif args.net:
        launch_network(dconf.Lab2_Tests+args.testfile, args.pcalgorithm)
        
            
