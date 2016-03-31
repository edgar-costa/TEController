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

H10 = 'h10'
H11 = 'h11'
H12 = 'h12'

H20 = 'h20'
H21 = 'h21'
H22 = 'h22'

H30 = 'h30'
H31 = 'h31'
H32 = 'h32'

H40 = 'h40'
H41 = 'h41'
H42 = 'h42'

M1 = 'm1'

BW = 1  # Absurdly low bandwidth for easy congestion (in Mb)

class Lab1Topo(IPTopo):
    def build(self, testfile, *args, **kwargs):
        """
            +--+         +--+  +--+
            |S4|         |D |  |T |
   +--+     +--+         +--+  +--+
   |S3|___    |           |   __/
   +--+   \_+---+        +---+    +--+
            | R2|--------|R3 |----|X |
            +---+       /+---+__  +--+
              |     ___/   |    \__+--+
           10 |    /       |       |Y |
              |   /        |       +--+
 +--+      +----+'       +---+      +--+
 |S1|------| R1 |--------| R4|------|C1|
 +--+     _+----+       _+---+_     +--+
        _/    |       _/   |   \_
    +--+    +---+   +--+  +--+   \+---+
    |M1|    |S2 |   |S5|  |TG|    |LBC|
    +--+    +---+   +--+  +--+    +---+
        """
        # Add routers and router-router links
        r1 = self.addRouter(R1, cls=MyCustomRouter)
        r2 = self.addRouter(R2, cls=MyCustomRouter)
        r3 = self.addRouter(R3, cls=MyCustomRouter)
        r4 = self.addRouter(R4, cls=MyCustomRouter)

        self.addLink(r1, r2, cost=10)
        self.addLink(r1, r4)
        self.addLink(r2, r3)
        self.addLink(r3, r4)
        self.addLink(r1, r3)

        # Create broadcast domains
        self.addLink(r1, self.addHost(H10)) 
        self.addLink(r1, self.addHost(H11)) 
        self.addLink(r1, self.addHost(H12)) 

        self.addLink(r2, self.addHost(H20))  
     	self.addLink(r2, self.addHost(H21))  
        self.addLink(r2, self.addHost(H22))  

        self.addLink(r3, self.addHost(H30))
        self.addLink(r3, self.addHost(H31))
        self.addLink(r3, self.addHost(H32))
        
        self.addLink(r4, self.addHost(H40))
        self.addLink(r4, self.addHost(H41))
        self.addLink(r4, self.addHost(H42))

        # Adding Fibbing Controller
        c1 = self.addController(C1, cfg_path=C1_cfg)
        self.addLink(c1, r4, cost=1000)

        # Adding Traffic Generator Host
        c2 = self.addHost(TG, isTrafficGenerator=True, flowfile=testfile) 
        self.addLink(c2, r4)

        # Adding Traffic Engineering Controller
        c3 = self.addHost(LBC, isLBController=True, algorithm='lab2')
        self.addLink(c3, r4)


class Lab1Topo2(IPTopo):
    def build(self, testfile, *args, **kwargs):

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
        c3 = self.addHost(LBC, isLBController=True, algorithm='lab2')
        self.addLink(c3, r4)

        
def launch_network(testfile):
    net = IPNet(topo = Lab1Topo(testfile),
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
        launch_network(dconf.Lab1_Tests+args.testfile)
        
            
