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

C1_cfg = '/tmp/c1.cfg'

C1 = 'c1' #fibbing controller
TG = dconf.TG_Hostname #traffic generator
LBC = dconf.LBC_Hostname #Load Balancing controller

R1 = 'r1'
R2 = 'r2'
R3 = 'r3'
R4 = 'r4'

D1 = 'd1'
D2 = 'd2'
D3 = 'd3'
D4 = 'd4'

S1 = 's1'
S2 = 's2'
S3 = 's3'
S4 = 's4'
S5 = 's5'


M1 = 'm1'

BW = 1  # Absurdly low bandwidth for easy congestion (in Mb)

SIG_TOPO = """
            +---+        +----+    +---+
            |S4 |        | D1 |    | D3|
   +--+     +---+        +----+  __+---+
   |S3|___    |           |   __/
   +--+   \_+---+        +---+      +---+
            | R2|--------|R3 |------|D2 |
            +---+       /+---+__    +---+
              |     ___/   |    \___+---+
           10 |    /       |        |D4 |
              |   /        |        +---+
 +--+      +----+'       +---+        +--+
 |S1|------| R1 |--------| R4|--------|C1|
 +--+     _+----+        +---+_       +--+
        _/    |            |   \__
   +---+    +---+        +---+    \+---+
   | M1|    |S2 |        |TG |     |LBC|
   +---+    +---+        +---+     +---+
        """

class snmpTestTopo(IPTopo):
    def build(self, *args, **kwargs):
        """       +---+
               ___|R3 |__
            3 /   +---+  \3
             /            \
 +--+      +----+   10   +---+        +--+
 |S1|------| R1 |--------| R2|--------|D1|
 +--+      +----+        +---+_       +--+
              |            |   \_  
            +---+        +---+   +---+
            |C1 |        |LBC|   |TG |
            +---+        +---+   +---+
        """
        r1 = self.addRouter(R1, cls=MyCustomRouter)
        r2 = self.addRouter(R2, cls=MyCustomRouter)
        r3 = self.addRouter(R3, cls=MyCustomRouter)
        self.addLink(r1, r2, cost = 10)
        self.addLink(r1, r3, cost = 3)
        self.addLink(r3, r2, cost = 3)
        
        s1 = self.addHost(S1)
        d1 = self.addHost(D1)

        self.addLink(s1, r1)
        self.addLink(d1, r2)

        # Adding Fibbing Controller
        c1 = self.addController(C1, cfg_path=C1_cfg)
        self.addLink(c1, r1, cost = 1000)


        
class SimpleTopo(IPTopo):
    def build(self, *args, **kwargs):
        """       +---+         +---+
 +--+          ___|R3 |__       | D2|
 |S2|__     3 /   +---+  \3    _+---+
 +--+  \__   /            \   /
 +--+     \+----+   7   +---+        +--+
 |S1|------| R1 |--------| R2|--------|D1|
 +--+     _+----+        +---+_       +--+
        _/    |            |   \_  
   +---+    +---+        +---+   +---+
   |M1 |    |C1 |        |LBC|   |TG |
   +---+    +---+        +---+   +---+
        """
        r1 = self.addRouter(R1, cls=MyCustomRouter)
        r2 = self.addRouter(R2, cls=MyCustomRouter)
        r3 = self.addRouter(R3, cls=MyCustomRouter)
        self.addLink(r1, r2, cost = 7)
        self.addLink(r1, r3, cost = 3)
        self.addLink(r3, r2, cost = 3)
        
        
        s1 = self.addHost(S1)
        s2 = self.addHost(S2)
        d1 = self.addHost(D1)
        d2 = self.addHost(D2)

        self.addLink(s1, r1)
        self.addLink(s2, r1)
        self.addLink(d1, r2)
        self.addLink(d2, r2)

        # Adding Fibbing Controller
        c1 = self.addController(C1, cfg_path=C1_cfg)
        self.addLink(c1, r1, cost = 1000)

        # Add Link Monitorer
        m1 = self.addHost(M1, isMonitorer=True)
        self.addLink(m1, r1)

        # Adding Traffic Generator Host
        c2 = self.addHost(TG, isTrafficGenerator=True)
        
        self.addLink(c2, r2)
        
        # Adding Traffic Engineering Controller
        c3 = self.addHost(LBC, isLBController=True)
        #c3 = self.addHost(LBC, isLBController=True, algorithm='SimplePath')
        #c3 = self.addHost(LBC, isLBController=True, algorithm='ECMP')
        self.addLink(c3, r2) 



        
class SIGTopo(IPTopo):
    def build(self, *args, **kwargs):
        """
            +--+         +--+  +--+
            |S4|         |D1|  |D3|
   +--+     +--+         +--+  +--+
   |S3|___    |           |   __/
   +--+   \_+---+        +---+     +--+
            | R2|--------|R3 |-----|D2|
            +---+       /+---+__   +--+
              |     ___/   |    \__+--+
           10 |    /       |       |D4|
              |   /        |       +--+
 +--+      +----+'       +---+        +--+
 |S1|------| R1 |--------| R4|--------|C1|
 +--+     _+----+       _+---+_       +--+
        _/    |       _/   |   \_
    +--+    +---+   +--+  +--+   \+---+
    |M1|    |S2 |   |S5|  |TG|    |LBC|
    +--+    +---+   +--+  +--+    +---+
        """
        r1 = self.addRouter(R1, cls=MyCustomRouter)
        r2 = self.addRouter(R2, cls=MyCustomRouter)
        r3 = self.addRouter(R3, cls=MyCustomRouter)
        r4 = self.addRouter(R4, cls=MyCustomRouter)

        self.addLink(r1, r2, cost=10)
        self.addLink(r1, r4)
        self.addLink(r2, r3)
        self.addLink(r3, r4)
        self.addLink(r1, r3)

        s1 = self.addHost(S1)
        s2 = self.addHost(S2)
        s3 = self.addHost(S3)
        s4 = self.addHost(S4)
        s5 = self.addHost(S5)

        d1 = self.addHost(D1)
        d2 = self.addHost(D2)
        d3 = self.addHost(D3)
        d4 = self.addHost(D4)
        
        self.addLink(s1, r1)
        self.addLink(s2, r1)
        self.addLink(s3, r2)
        self.addLink(s4, r2)
        self.addLink(s5, r4)

        self.addLink(d1, r3)
        self.addLink(d2, r3)
        self.addLink(d3, r3)
        self.addLink(d4, r3)

        # Adding Fibbing Controller
        c1 = self.addController(C1, cfg_path=C1_cfg)
        self.addLink(c1, r4, cost=999)

        # Add Link Monitorer
        m1 = self.addHost(M1, isMonitorer=True)
        self.addLink(m1, r1)

        # Adding Traffic Generator Host
        c2 = self.addHost(TG, isTrafficGenerator=True) 
        self.addLink(c2, r4)

        # Adding Traffic Engineering Controller
        c3 = self.addHost(LBC, isLBController=True)
        #c3 = self.addHost(LBC, isLBController=True, algorithm='SimplePath')
        #c3 = self.addHost(LBC, isLBController=True, algorithm='ECMP')
        self.addLink(c3, r4)

        

def launch_network():
    print SIG_TOPO
    net = IPNet(topo=SIGTopo(),
                debug=_lib.DEBUG_FLAG,
                intf=custom(TCIntf, bw=BW),
                host=MyCustomHost)
    
    TopologyDB(net=net).save(dconf.DB_Path)
    net.start()
    FibbingCLI(net)
    net.stop()



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-n', '--net',
                       help='Start the Mininet topology',
                       action='store_true',
                       default=True)
    parser.add_argument('-d', '--debug',
                        help='Set log levels to debug',
                        action='store_true',
                        default=False)
    args = parser.parse_args()

    if args.debug:
        _lib.DEBUG_FLAG = True
        from mininet.log import lg
        from fibbingnode import log
        import logging
        log.setLevel(logging.DEBUG)
        lg.setLogLevel('debug')
    elif args.net:
        launch_network()
