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
import ipaddress

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
        try:
            self._lbc_ip = ipaddress.ip_interface(self.getHostIPByName(dconf.LBC_Hostname)).ip.compressed
        except:
            log.info("WARNING: Load balancer controller could not be found in the network\n")
            self._lbc_ip = None
            
    def getHostIPByName(self, hostname):
        """Searches in the topology database for the hostname's ip address.
        """
        if hostname not in self.db.network.keys():
            return None
        else:
            ip = [v['ip'] for k, v in self.db.network[hostname].iteritems() if isinstance(v, dict)][0]
            return ip

        
    def informLBController(self, flow):
        """Part of the code that deals with the JSON interface to inform to
        LBController a new flow created in the network.
        """
        url = "http://%s:%s/newflowstarted" %(self._lbc_ip, dconf.LBC_JsonPort)
        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info('%s - Informing LBController...\n'%t)
        log.info('\t   * Flow: %s\n'%self.toLogFlowNames(flow))
        log.info('\t   * URL: %s\n'%url)

        try:
            requests.post(url, json = flow.toJSON())
        except Exception:
            log.info("ERROR: LBC could not be informed!\n")
            log.info("LOG: Exception in user code:\n")
            log.info('-'*60+'\n')
            log.info(traceback.print_exc())
            log.info('-'*60+'\n')            

    def toLogFlowNames(self, flow):
        a = "(%s -> %s): %s, t_o: %s, duration: %s" 
        return a%(self.getNameFromIP(flow.src.compressed),
                  self.getNameFromIP(flow.dst.compressed),
                  flow.setSizeToStr(flow.size),
                  flow.setTimeToStr(flow.start_time),
                  flow.setTimeToStr(flow.duration))

    def getNameFromIP(self, x):
        """Returns the name of the host or the router given the ip of the
        router or the ip of the router's interface towards that
        subnet.
        """
        if x.find('/') == -1: # it means x is a router id
            ip_router = ipaddress.ip_address(x)
            name = [name for name, values in
                    self.db.network.iteritems() if values['type'] ==
                    'router' and
                    ipaddress.ip_address(values['routerid']) ==
                    ip_router][0]
            return name
        
        elif 'C' not in x: # it means x is an interface ip and not the
                           # weird C_0
            ip_iface = ipaddress.ip_interface(x)
            for name, values in self.db.network.iteritems():
                if values['type'] != 'router' and values['type'] != 'switch':
                    for key, val in values.iteritems():    
                        if isinstance(val, dict):
                            ip_iface2 = ipaddress.ip_interface(val['ip'])
                            if ip_iface.ip == ip_iface2.ip:
                                return name
                else:
                    return None

    def createFlow(self, flow):
        """Calls _createFlow in a different Thread (for efficiency)
        """
        t = Thread(target=self._createFlow, args=(flow,)).start()
        
    def _createFlow(self, flow):
        """Creates the corresponding iperf command to actually install the
        given flow in the network.  This function has to call
        self.informLBController!
        """
        # Sleep after it is your time to start
        time.sleep(flow['start_time'])

        # Create new flow with hosts ip's instead of interfaces
        # Iperf only understands ip's
        flow2 = Flow(src = flow['src'].ip.compressed,
                     dst = flow['dst'].ip.compressed,
                     sport = flow['sport'],
                     dport = flow['dport'],
                     size = flow['size'],
                     start_time = flow['start_time'],
                     duration = flow['duration'])
        
        url = "http://%s:%s/startflow" %(flow2['src'], dconf.Hosts_JsonPort)

        t = time.strftime("%H:%M:%S", time.gmtime())
        log.info('%s - _createFlow(): starting Flow - Sending request to host\n'%t)
        log.info('\t   * FLOW (sent to Host): %s\n'%self.toLogFlowNames(flow))
        log.info('\t   * URL: %s\n'%url)

        # Send request to host to start new iperf client session
        try:
            requests.post(url, json = flow2.toJSON())
        except Exception:
            log.info("ERROR: Request could not be sent to Host!\n")
            log.info("LOG: Exception in user code:\n")
            log.info('-'*60+'\n')
            log.info(traceback.print_exc())
            log.info('-'*60+'\n')
            
        # Call to informLBController if it is active
        if self._lbc_ip:
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
        if flows:
            for flowline in flows:
                flowline = flowline.replace(' ','').replace('\n','')
                if flowline != '' and flowline[0] != '#':
                    try:
                        [s, d, sp, dp, size, s_t, dur] = flowline.strip('\n').split(',')
                        # Get hosts IPs
                        src_iface = self.getHostIPByName(s)
                        dst_iface = self.getHostIPByName(d)
                    except Exception:
                        log.info("EP, SOMETHING HAPPENS HERE\n")
                        src_iface = None
                        dst_iface = None
                        
                    if src_iface != None and dst_iface != None:
                        flow = Flow(src = src_iface,
                                    dst = dst_iface,
                                    sport = sp,
                                    dport = dp,
                                    size = size,
                                    start_time = s_t,
                                    duration = dur)
                        #Schedule flow creation
                        self.scheduler.enter(0, 1, self.createFlow, ([flow]))
                    else:
                        log.info("ERROR! Hosts %s and/or %s do not exist in the network!\n"%(s, d))                       
                        
            # Make the scheduler run after file has been parsed
            self.scheduler.run()
        else:
            log.info("No flows to schedule in file\n")                

                            
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
    # Wait for the network to be created correcly: IP's assigned, etc.
    time.sleep(dconf.TG_InitialWaitingTime)

    # Get Traffic Generator hosts's IP.
    MyOwnIp = tg.getHostIPByName(dconf.TG_Hostname).split('/')[0]
    t = time.strftime("%H:%M:%S", time.gmtime())
    log.info("%s - TRAFFIC GENERATOR - HOST %s\n"%(t, MyOwnIp))
    log.info("-"*60+"\n")

    # Start the traffic generator object
    tg = TrafficGenerator()
    
    # Schedule flows from file
    flowfile = dconf.FlowFile

    t = time.strftime("%H:%M:%S", time.gmtime())
    st = time.time()
    log.info("%s - main(): Scheduling flow file: %s ...\n"%(t, flowfile))

    tg.scheduleFileFlows(flowfile)
    
    t2 = time.strftime("%H:%M:%S", time.gmtime())
    log.info("%s - main(): Scheduled flow file after %.3f seconds\n"%(t2, time.time()-st))

    # Go start the JSON API server and listen for commands
    app = create_app(app, tg)
    app.run(host=MyOwnIp)






    
