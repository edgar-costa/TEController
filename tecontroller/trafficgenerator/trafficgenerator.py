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
import copy
import sys, traceback

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
        url = "http://%s:%s/newflowstarted" %(self._lbc_ip, dconf.LBC_JsonPort)
        log.info(' * Informing LBController...\n')
        log.info('   - Flow: %s\n'%str(flow))
        log.info('   - URL: %s\n'%url)
        try:
            requests.post(url, json = flow.toJSON())
        except Exception:
            log.info("ERROR: LBC could not be informed!\n")
            log.info("LOG: Exception in user code:\n")
            log.info('-'*60+'\n')
            log.info(traceback.print_exc())
            log.info('-'*60+'\n')            

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
        flow_cpy = copy.deepcopy(flow)
        flow_cpy['src'] = flow['src'].compressed.split('/')[0]
        flow_cpy['dst'] = flow['dst'].compressed.split('/')[0]
        
        url = "http://%s:%s/startflow" %(flow_cpy['src'], dconf.Hosts_JsonPort)
        log.info('LOG: TrafficGenerator - starting Flow:\n')
        log.info(' * Sending request to host\n')
        log.info('   - FLOW (sent to Host): %s\n'%str(flow_cpy))
        log.info('   - URL: %s\n'%url)

        # Send request to host to start new iperf client session
        try:
            requests.post(url, json = flow_cpy.toJSON())
        except Exception:
            log.info("ERROR: Request could not be sent to Host!\n")
            log.info("LOG: Exception in user code:\n")
            log.info('-'*60+'\n')
            log.info(traceback.print_exc())
            log.info('-'*60+'\n')
            
        # Call to informLBController 
        self.informLBController(flow)
        
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
            try:
                [s, d, sp, dp, size, s_t, dur] = flowline.strip('\n').split(',')
                srcip = self.getHostIPByName(s)
                dstip = self.getHostIPByName(d)
            except Exception:
                srcip = None
                dstip = None
            if srcip != None and dstip != None:
                flow = Flow(src = srcip,
                            dst = dstip,
                            sport = sp,
                            dport = dp,
                            size = size,
                            start_time = s_t,
                            duration = dur)
                #Schedule flow creation
                self.scheduler.enter(flow['start_time'], 1, self._createFlow, ([flow]))
            else:
                log.info("ERROR! Hosts %s and/or %s do not exist in the network!\n"%(s, d))
                
        self.scheduler.run()

def create_app(appl, traffic_generator):
    app.config['TG'] = traffic_generator
    return appl

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
        log.info("ERROR: could not create flow:\n")
        log.info(" * %s\n"%flow)
        log.info(traceback.format_exc())

        
if __name__ == '__main__':

    # Start the traffic generator object
    tg = TrafficGenerator()

    # Wait for the network to be created correcly: IP's assigned, etc.
    time.sleep(dconf.TG_InitialWaitingTime)
    
    # Get Traffic Generator hosts's IP.
    MyOwnIp = tg.getHostIPByName(dconf.TG_Hostname).split('/')[0]
    log.info("TRAFFIC GENERATOR - HOST %s\n"%(MyOwnIp))
    log.info("-"*60+"\n")

    # Schedule flows from file
    flowfile = dconf.FlowFile
    #flowfile = dconf.TG_Path + 'flowfile2.csv'
    tg.scheduleFileFlows(flowfile)
    log.info("LOG: Scheduled flow file: %s\n"%flowfile)
    
    # Go start the JSON API server and listen for commands
    app = create_app(app, tg)
    app.run(host=MyOwnIp)



    
