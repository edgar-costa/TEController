#!/usr/bin/python
import sched
import time
from fibbingnode.misc.mininetlib.ipnet import TopologyDB
from fibbingnode.misc.mininetlib import get_logger
from flow import Flow, Base
from threading import Thread 
from time import sleep
import requests
import json

import flask
app = flask.Flask(__name__)

TEControllerJsonPort = '5000'
HostDefaultJsonPort = '5000'

FlowFile = 'flowfile.csv'
TG_path = '/root/fibbingnode/fibbingnode/trafficgenerator/'
DB_path = '/tmp/db.topo'

TEC = 'c2' #TODO: CHANGE TO C3 when TEC is created!!

# logger to log to the mininet cli
log = get_logger()


class TrafficGenerator(Base):
    """Object that creates a Traffic Generator in the network.

    """
    def __init__(self, *args, **kwargs):
        super(TrafficGenerator, self).__init__(*args, **kwargs)
        
        self.scheduler = sched.scheduler(time.time, time.sleep)
        self.db = TopologyDB(db=DB_path)
        #IP of the Traffic Engineering Controller. It must be set
        #above to 'c3' instead of 'c2'
        #self._tec_ip = self.getHostIPByName(TEC)


    def getHostIPByName(self, hostname):
        """Searches in the topology database for the hostname's ip address.

        """
        if hostname not in self.db.network.keys():
            return None

        else:
            routers = [r for r in self.db.network.keys() if 'r' in r]
            ip = [self.db.interface(hostname, r) for r in routers if r in self.db.network[hostname].keys()]
            return str(ip[0]).split('/')[0]    


    def informTEController(self, flow):
        """Part of the code that deals with the JSON interface to inform to
        TEController a new flow created in the network.

        """
        url = "http://%s:%s/newflowstarted" %(self._tec_ip, TEControllerJsonPort)
        requests.post(url, json = flow.toJSON())


    def createFlow(self, flow):
        """Calls _createFlow in a different Thread (for efficiency)
        """
        t = Thread(target=self._createFlow, args=(flow,)).start()
        
    def _createFlow(self, flow):
        """Creates the corresponding iperf command to actually install the
        given flow in the network.  This function has to call
        self.informTEController!

        """
        hostIP = flow['src']
        url = "http://%s:%s/startflow" %(hostIP, HostDefaultJsonPort)
        log.info('TrafficGenerator - starting Flow:\n')
        log.info('\t%s\n'%str(flow))
        requests.post(url, json = flow.toJSON())
        # TODO: a call to informTEController should be added here
        #self.informController(flow)
        
    def createRandomFlow(self):
        """Creates a random flow in the network

        """
        pass

    def scheduleRandomFlows(self, ex_time = 60, max_size = "40M"):
        """Creates a random schedule of random flows in the network. This will
        be useful later to evaluate the performance of the
        TEController.

        """
        pass

    def scheduleFileFlows(self, flowfile):
        """Schedules the flows specified in the flowfile
        """
        f = open(flowfile, 'r')
        flows = f.readlines()
        for flowline in flows:
            [s, d, sp, dp, size, start_time, duration] = flowline.strip('\n').split(',')
            srcip = self.getHostIPByName(s)
            dstip = self.getHostIPByName(d)
            flow = Flow(srcip, dstip, sp, dp, size, start_time, duration)
            self.scheduler.enter(flow['start_time'], 1, self.createFlow, ([flow]))

        self.scheduler.run()


def create_app(app, traffic_generator):
    app.config['TG'] = traffic_generator
    return app


@app.route("/startflow", methods = ['POST'])
def trafficGeneratorCommandListener():
    """This function will be running in each of the hosts in our
    network. It essentially waits for commands from the
    TrafficGenerator in the Json-Rest interface and creates a
    subprocess for each corresponding iperf client sessions to other
    hosts.
    """
    # Fetch json data
    flow_tmp = flask.request.json
    
    # Fetch the TG Object
    tg = app.config['TG']

    # Create flow from json data.
    #Beware that hosts in flowfile are given by hostnames: s1,d2, etc.
    src = tg.getHostIPByName(flow_tmp['src'])
    dst = tg.getHostIPByName(flow_tmp['dst'])
    flow = Flow(src, dst, flow_tmp['sport'], flow_tmp['dport'],
                flow_tmp['size'], flow_tmp['start_time'], flow_tmp['duration'])
    try:
        tg.createFlow(flow)
    except Exception, err:
        print flow
        print(traceback.format_exc())

        
if __name__ == '__main__':
    # Wait for the network to be created correcly: IP's assigned, etc.
    sleep(20)
    # Start the traffic generator object
    tg = TrafficGenerator()

    # Get Traffic Generator hosts's IP. We assume it's allways in 'c2'
    MyOwnIp = tg.getHostIPByName('c2')
    
    # Schedule flows from file
    tg.scheduleFileFlows(TG_path+FlowFile)

    # Go start the JSON API server and listen for commands
    app = create_app(app, tg)
    app.run(host=MyOwnIp)



    
