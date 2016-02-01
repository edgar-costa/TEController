#!/usr/bin/python

"""This module defines a traffic generator script to be executed in
the Traffic Generator host in the mininet network.

Essentially, reads from a flow definition file and schedules the
traffic.

When a new flow must be created: 

 - Sends commands to corresponding hosts to start exchanging data using
  iperf.

 - Informs the LBController through a JSON interface

After scheduling all flows defined in the file, it opens a JSON-flesk
server to wait for further commands.
"""

from fibbingnode.misc.mininetlib.ipnet import TopologyDB
from fibbingnode.misc.mininetlib import get_logger

from tecontroller.res.flow import Flow, Base
from tecontroller.res import defaultconf as dconf

from threading import Thread 
import time
import requests
import sched
import json


import flask
app = flask.Flask(__name__)

# logger to log to the mininet cli
log = get_logger()


class TrafficGenerator(Base):
    """Object that creates a Traffic Generator in the network.
    """
    def __init__(self, *args, **kwargs):
        super(TrafficGenerator, self).__init__(*args, **kwargs)
        
        self.scheduler = sched.scheduler(time.time, time.sleep)
        self.db = TopologyDB(db=dconf.DB_Path)
        
        #IP of the Load Balancer Controller host.
        self._lbc_ip = self.getHostIPByName(dconf.LBC_Hostname).split('/')[0]

    def getHostIPByName(self, hostname):
        """Searches in the topology database for the hostname's ip address.
        """
        if hostname not in self.db.network.keys():
            return None
        else:
            routers = [r for r in self.db.network.keys() if 'r' in r]
            ip = [self.db.interface(hostname, r) for r in routers if r
                  in self.db.network[hostname].keys()]
            return str(ip[0])    


    def informLBController(self, flow):
        """Part of the code that deals with the JSON interface to inform to
        LBController a new flow created in the network.
        """
        url = "http://%s:%s/newflowstarted" %(self._lbc_ip, LBC_JsonPort)
        requests.post(url, json = flow.toJSON())

    def createFlow(self, flow):
        """Calls _createFlow in a different Thread (for efficiency)
        """
        t = Thread(target=self._createFlow, args=(flow,)).start()
        
    def _createFlow(self, flow):
        """Creates the corresponding iperf command to actually install the
        given flow in the network.  This function has to call
        self.informLBController!

        """
        # Remove the interface mask part from the addresses, because
        # hosts only recognise their IP, not their interface ip.
        flow_cpy = flow
        flow_cpy['src'] = flow['src'].split('/')[0]
        flow_cpy['dst'] = flow['dst'].split('/')[0]
        
        url = "http://%s:%s/startflow" %(flow_cpy['src'], dconf.Hosts_JsonPort)
        log.info('TrafficGenerator - starting Flow:\n')
        log.info('\t%s\n'%str(flow))
        requests.post(url, json = flow_cpy.toJSON())

        # Call to informLBController 
        self.informController(flow)
        
    def createRandomFlow(self):
        """Creates a random flow in the network

        """
        pass

    def scheduleRandomFlows(self, ex_time = 60, max_size = "40M"):
        """Creates a random schedule of random flows in the network. This will
        be useful later to evaluate the performance of the
        LBController.
        """
        pass

    def scheduleFileFlows(self, flowfile):
        """Schedules the flows specified in the flowfile
        """
        f = open(flowfile, 'r')
        flows = f.readlines()
        for flowline in flows:
            [s, d, sp, dp, size, s_t, dur] = flowline.strip('\n').split(',')
            srcip = self.getHostIPByName(s)
            dstip = self.getHostIPByName(d)
            flow = Flow(src = srcip,
                        dst = dstip,
                        sport = sp,
                        dport = dp,
                        size = size,
                        start_time = s_t,
                        duration = dur)
            #Schedule flow creation
            self.scheduler.enter(flow['start_time'], 1, self._createFlow, ([flow]))

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
        tg._createFlow(flow)
    except Exception, err:
        print flow
        print(traceback.format_exc())

        
if __name__ == '__main__':
    # Wait for the network to be created correcly: IP's assigned, etc.
    time.sleep(dconf.InitialWaitingTime)
    
    # Start the traffic generator object
    tg = TrafficGenerator()

    # Get Traffic Generator hosts's IP.
    MyOwnIp = tg.getHostIPByName(dconf.TG_Hostname)
    
    # Schedule flows from file
    tg.scheduleFileFlows(dconf.FlowFile)

    # Go start the JSON API server and listen for commands
    app = create_app(app, tg)
    app.run(host=MyOwnIp)



    
