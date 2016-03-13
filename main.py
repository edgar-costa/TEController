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
        # Create routers
        r1 = self.addRouter(R1, cls=MyCustomRouter)
        r2 = self.addRouter(R2, cls=MyCustomRouter)
        r3 = self.addRouter(R3, cls=MyCustomRouter)
        self.addLink(r1, r3, cost = 4)
        self.addLink(r3, r2, cost = 4)
        self.addLink(r1, r2, cost = 7)

        # Create sources
        s1 = self.addHost(S1)
        s2 = self.addHost(S2)
        self.addLink(s1, r1)
        self.addLink(s2, r1)

        # Create destinations
        sw1 = self.addSwitch('sw1')
        self.addLink(sw1, self.addHost('d1'))
        self.addLink(sw1, self.addHost('d2'))
        self.addLink(sw1, self.addHost('d3'))
        self.addLink(sw1, r2)
        
        sw2 = self.addSwitch('sw2')
        self.addLink(sw2, self.addHost('t1'))
        self.addLink(sw2, self.addHost('t2'))
        self.addLink(sw2, self.addHost('t3'))
        self.addLink(sw2, r2)

        # Adding Fibbing Controller
        c1 = self.addController(C1, cfg_path=C1_cfg)
        self.addLink(c1, r1, cost = 1000)

        # Add Link Monitorer
        #m1 = self.addHost(M1, isMonitorer=True)
        #self.addLink(m1, r1)

        # Adding Traffic Generator Host
        #c2 = self.addHost(TG, isTrafficGenerator=True)
        #self.addLink(c2, r2)
        
        # Adding Traffic Engineering Controller
        c3 = self.addHost(LBC, isLBController=True, algorithm='SimplePath')
        self.addLink(c3, r2) 

        
        
class SIGTopo(IPTopo):
    def build(self, *args, **kwargs):
        """
            +--+         +---+  +---+
            |S4|         |D's|  |T's|
   +--+     +--+         +--+   +---+
   |S3|___    |           |   __/
   +--+   \_+---+        +---+     +---+
            | R2|--------|R3 |-----|X's|
            +---+       /+---+__   +---+
              |     ___/   |    \__+---+
           10 |    /       |       |Y's|
              |   /        |       +---+
 +--+      +----+'       +---+        +--+
 |S1|------| R1 |--------| R4|--------|C1|
 +--+     _+----+       _+---+_       +--+
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
        sw1 = self.addSwitch('sw1')
        self.addLink(sw1, self.addHost('d1'))
        self.addLink(sw1, self.addHost('d2'))
        self.addLink(sw1, self.addHost('d3'))
        self.addLink(sw1, r3)
        
        sw2 = self.addSwitch('sw2')
        self.addLink(sw2, self.addHost('t1'))
        self.addLink(sw2, self.addHost('t2'))
        self.addLink(sw2, self.addHost('t3'))
        self.addLink(sw2, r3)

        sw3 = self.addSwitch('sw3')
        self.addLink(sw3, self.addHost('x1'))
        self.addLink(sw3, self.addHost('x2'))
        self.addLink(sw3, self.addHost('x3'))
        self.addLink(sw3, r3)

        sw4 = self.addSwitch('sw4')
        self.addLink(sw4, self.addHost('y1'))
        self.addLink(sw4, self.addHost('y2'))
        self.addLink(sw4, self.addHost('y3'))
        self.addLink(sw4, r3)

        s1 = self.addHost(S1)
        s2 = self.addHost(S2)
        s3 = self.addHost(S3)
        s4 = self.addHost(S4)

        self.addLink(s1, r1)
        self.addLink(s2, r1)
        self.addLink(s3, r2)
        self.addLink(s4, r2)
        
        # Adding Fibbing Controller
        c1 = self.addController(C1, cfg_path=C1_cfg)
        self.addLink(c1, r4, cost=1000)

        # Add Link Monitorer
        m1 = self.addHost(M1, isMonitorer=True)
        self.addLink(m1, r1)

        # Adding Traffic Generator Host
        c2 = self.addHost(TG, isTrafficGenerator=True) 
        self.addLink(c2, r4)

        # Adding Traffic Engineering Controller
        #c3 = self.addHost(LBC, isLBController=True)
        c3 = self.addHost(LBC, isLBController=True, algorithm='SimplePath')
        #c3 = self.addHost(LBC, isLBController=True, algorithm='ECMP')
        self.addLink(c3, r4)

        

def launch_network():
    #signal.signal(signal.SIGINT, signal_handler)
    #signal.signal(signal.SIGTERM, signal_handler)
    
    net = IPNet(topo=SIGTopo(),
                debug=_lib.DEBUG_FLAG,
                intf=custom(TCIntf, bw=BW),
                host=MyCustomHost)
    
    TopologyDB(net=net).save(dconf.DB_Path)
    net.start()
    fcli = FibbingCLI(net)
    net.stop()    

def signal_handler(signal, frame):
    print ("Execution inside '{0}', " "with local namespace: {1}"
           .format(frame.f_code.co_name, frame.f_locals.keys()))
    print ("who is self?: {0}".format(frame.f_locals['self'].__class__))
    fcli = frame.f_locals['self']
    line = frame.f_locals['line']
    import ipdb; ipdb.set_trace()
    fcli.do_EOF(line)
    sys.stdout.write("EOF\n")
    sys.stdout.write("Signal catched!\n")
    

def launch_controller():
    CFG.read(C1_cfg)
    db = TopologyDB(db='/tmp/db.topo')
    manager = SouthboundManager(optimizer=OSPFSimple())
        
    import ipdb; ipdb.set_trace()
    manager.simple_path_requirement(db.subnet(R3, D1), [db.routerid(r)
                                                        for r in (R1, R2, R3)])
    try:
        manager.run()
    except KeyboardInterrupt:
        manager.stop()

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
        launch_network()
