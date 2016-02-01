#!/usr/bin/python

"""This script is intended to be spawned as an independent thread by tecontroller.

It basically listens for information sent by the traffic generator
through a flesk interface.

Upon receiving a new flow notificaiton, puts the event inside the
shared queue eventQueue.
"""
from tecontroller.res.flow import Flow
from tecontroller.loadbalancer.lbcontroller import DatabaseHandler
from fibbingnode.misc.mininetlib import get_logger
from tecontroller.loadbalancer import shared
from tecontroller.res import defaultconf as dconf
import netifaces as ni
import time

from tecontroller.res import defaultconf as dconf

import flask 
app = flask.Flask(__name__)

log = get_logger()

@app.route("/newflowstarted", methods = ['POST'])
def newFlowStarted():
    req = flask.request.json
    log.info("LOG: newFlowStarted was executed\n")
    log.info(" * Request received: %s\n"%str(req))
    
    flow = Flow(req['src'], req['dst'], req['sport'], req['dport'],
                req['size'], req['start_time'], req['duration'])
    newFlowStartedEvent = {'type': 'newFlowStarted', 'data': flow}
    shared.eventQueue.put(newFlowStartedEvent, block=True)
    log.info("DO I GET HERE? YES\n")
    shared.eventQueue.task_done()

if __name__ == "__main__":
    #Searching for the interface's IP addr
    MyETH0Iface = 'c3-eth0'
    ni.ifaddresses(MyETH0Iface)
    MyOwnIp = ni.ifaddresses(MyETH0Iface)[2][0]['addr']

    #Start the flesk app under public ip and default json port
    log.info('LBC JSON LISTENER - HOST %s - IFACE %s\n'%(MyOwnIp, MyETH0Iface))
    log.info("-"*60+"\n")
    app.run(host=MyOwnIp, port=dconf.LBC_JsonPort)
