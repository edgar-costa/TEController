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
import mininet.node as _node

TG_PATH = '/tecontroller/trafficgenerator/'
TEC_PATH = '/tecontroller/tecontroller/'

logfolder = "./logs/"
iperf_logfile = logfolder + "%s_iperf.log"
daemon_logfile = logfolder + "%s_daemon.log"
tg_logfile = logfolder + "TG.log"

defaultIperfPort = '5001'

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
            tg = self.popen(TG_PATH+'trafficgenerator.py',
                                           stdin=None, stdout=tgl, stderr=tgl)
            
        elif 'isTrafficEngineeringController' in kwargs.keys() and kwargs.get('isTrafficEngineeringController') == True:
            log.info("Starting Traffic Engineer Controller\n")
            
            tec = self.popen(TEC_PATH+'tecontroller.py', stdin=None,
                             stdout=None, stderr=None)

        else: #Just a normal host in the network
            iperf_file = iperf_logfile % (self.name)
            daemon_file = daemon_logfile % (self.name)
            i = open(iperf_file, 'w')
            d = open(daemon_file, 'w')
            
            #Spawn the iperf server process
            log.info('Host %s: Creating iperf server process, port %s\n'%(self.name, defaultIperfPort))
            iperf_server_process = self.popen('iperf', '-u', '-s',
                                              '-p', defaultIperfPort,
                                              '-i', '1', stdin=None,
                                              stdout=i, stderr=i)

            #Spawn the custom daemon process
            log.info('Host %s: Creating custom daemon process\n'%self.name)
            custom_daemon_process = self.popen(TG_PATH + 'customiperfdaemon.py',
                                               stdin=None, stdout=d, stderr=d)
            
            i.close()
            d.close()
