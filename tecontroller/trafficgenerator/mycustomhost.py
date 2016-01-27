"""This module defines a custom class for the hosts created in a mininet
networ. Essentially redefines the mininet nodes by extending its
__init__ method.

We allow for 3 different types of MyCustomHost to be created:

 - Normal custom hosts: they will spawn an iperf server daemon and a
   custom daemon that listens for traffic generation orders from the
   traffic generator.

 - Traffic Generator: it spawns the traffic generator script inside
   the newly created host.

 - Traffic Engineering Controller. it spawns the traffic engineering
   controller inside the newly created host.

"""

from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res import defaultconf as dconf
import mininet.node as _node

iperf_logfile = dconf.Hosts_LogFolder + "%s_iperf.log"
daemon_logfile = dconf.Hosts_LogFolder + "%s_daemon.log"
tg_logfile = dconf.Hosts_LogFolder + "TG.log"

log = get_logger()

class MyCustomHost(_node.Host):
    """This class essentially extends the Host class in mininet so that
    our custom hosts create the two desired processes in each host:

    - The iperf server

    - The custom daemon process that waits for commands from the
      JSON-Rest API
    """
    def __init__(self, *args, **kwargs):
        super(MyCustomHost, self).__init__(*args, **kwargs)

        if 'isTrafficGenerator' in kwargs.keys() and kwargs.get('isTrafficGenerator') == True:
            log.info("Starting Traffic Generator\n")
            tgl = open(tg_logfile, 'w')
            tg = self.popen(dconf.TG_Path+'trafficgenerator.py',
                                           stdin=None, stdout=tgl, stderr=tgl)
            
        elif 'isLBController' in kwargs.keys() and kwargs.get('isLBController') == True:
            log.info("Starting LoadBalancing Controller\n")
            
            tec = self.popen(dconf.LBC_Path+'lbcontroller.py', stdin=None,
                             stdout=None, stderr=None)
            
        else: #Just a normal host in the network
            iperf_file = iperf_logfile % (self.name)
            daemon_file = daemon_logfile % (self.name)
            i = open(iperf_file, 'w')
            d = open(daemon_file, 'w')
            
            #Spawn the iperf server process
            log.info('Host %s: Creating iperf server process, port %s\n'%(self.name, dconf.Hosts_DefaultIperfPort))
            iperf_server_process = self.popen('iperf', '-u', '-s',
                                              '-p', dconf.Hosts_DefaultIperfPort,
                                              '-i', '1', stdin=None,
                                              stdout=i, stderr=i)
            
            #Spawn the custom daemon process
            log.info('Host %s: Creating custom daemon process\n'%self.name)
            custom_daemon_process = self.popen(dconf.TG_Path +
                                               'customiperfdaemon.py',
                                               stdin=None, stdout=d,
                                               stderr=d)
            
            i.close()
            d.close()
