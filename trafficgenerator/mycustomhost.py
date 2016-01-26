import mininet.node as _node
from fibbingnode.misc.mininetlib import get_logger
from fibbingnode.trafficgenerator.trafficgenerator import TrafficGenerator

TG_PATH = '/root/fibbingnode/fibbingnode/trafficgenerator/'

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
            traffic_generator = self.popen(TG_PATH+'trafficgenerator.py',
                                           stdin=None, stdout=tgl, stderr=tgl)
        else:
            #now = datetime.datetime.now()
            #s = now.strftime("%m-%d_%H:%M")
            iperf_file = iperf_logfile % (self.name)#, s)
            daemon_file = daemon_logfile % (self.name)#, s)
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
