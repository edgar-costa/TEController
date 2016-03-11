#!/usr/bin/python
"""This python script defines the custom daemon that runs in the nodes
of the mininet network and allows them to receive orders from the
traffic generator.

This srcipt is meant to run as a daemon thread in each custom host
that is spawned at bootstrapping the host.

It basically listents for /startflow requests from the traffic
generator and creates the corresponding iperf client sessions that
generate the desired traffic in the network.

"""
from tecontroller.res import defaultconf as dconf
from tecontroller.res.flow import Base
from fibbingnode.misc.mininetlib import get_logger
from subprocess import Popen, PIPE
import time
import traceback
import netifaces as ni
import sys

import flask
app = flask.Flask(__name__)

log = get_logger()

@app.route("/startflow", methods = ['POST'])

def trafficGeneratorSlave():
    """This function will be running in each of the hosts in our
    network. It essentially waits for commands from the
    TrafficGenerator in the Json-Rest interface and creates a
    subprocess for each corresponding iperf client sessions to other
    hosts.

    """

    t = time.strftime("%H:%M:%S", time.gmtime())
    log.info("%s - StartFlow command from Traffic Generator arrived\n"%t)
    
    flow = flask.request.json
    aux = Base()
    size = aux.setSizeToStr(flow['size'])

    # Log it
    log.info("\t* Starting iperf client command...\n")
    log.info("\t  - src: %s:%s\n"%(flow['src'], flow['sport']))                
    log.info("\t  - dst: %s:%s\n"%(flow['src'], flow['dport']))
    log.info("\t  - size: %s\n"%size)
    log.info("\t  - duration: %s\n"%str(flow['duration']))

    Popen(["iperf", "-c", flow['dst'], "-u",
           "-b", size,
           "-t", str(flow['duration']),
           "-p", str(flow['dport'])])
    
if __name__ == "__main__":
    #Waiting for the IP's to be assigned...
    time.sleep(dconf.Hosts_InitialWaitingTime)
    
    #Searching for host's own interfaces
    proc = Popen(['netstat', '-i'], stdout=PIPE)
    ip_output = proc.stdout.readlines()
    ifaces = []
    MyETH0Iface = ""
    
    for index, line in enumerate(ip_output):
        ifaces.append(line.split(' ')[0])

    for i in ifaces:
        if 'eth0' in i:
            MyETH0Iface = i

    #Searching for the interface's IP addr
    ni.ifaddresses(MyETH0Iface)
    MyOwnIp = ni.ifaddresses(MyETH0Iface)[2][0]['addr']
    log.info("CUSTOM DAEMON - HOST %s - IFACE %s\n"%(MyOwnIp, MyETH0Iface))
    log.info("-"*60+"\n")
    app.run(host=MyOwnIp, port=dconf.Hosts_JsonPort)
