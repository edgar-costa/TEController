#!/usr/bin/python

"""This script is intended to be spawned as an independent thread by tecontroller.

It basically listens for information sent by the traffic generator
through a flesk interface.

Upon receiving a new flow notificaiton, puts the event inside the
shared queue eventQueue.
"""
from tecontroller.res.flow import Flow
from tecontroller.loadbalancer.lbcontroller import DatabaseHandler
from tecontroller.loadbalancer import shared
from tecontroller.res import defaultconf as dconf
import netifaces as ni
import time

from tecontroller.res import defaultconf as dconf

import flask 
app = flask.Flask(__name__)

@app.route("/newflowstarted", methods = ['POST'])
def newFlowStarted():
    req = flask.request.json

    flow = Flow(req['src'], req['dst'], req['sport'], req['dport'],
                req['size'], req['start_time'], req['duration'])

    newFlowStartedEvent = {'type': 'newFlowStarted', 'data': flow}
    shared.eventQueue.put(newFlowStartedEvent, block=True)
    shared.eventQueue.task_done()

if __name__ == "__main__":
    #Wait a bit until IP addresses have been assigned. We can do that,
    #since the Traffic Generator also waits some time before starting
    #to orchestraste traffic.
    time.sleep(dconf.InitialWaitingTime)
    
    #Searching for the interface's IP addr
    myETH0Iface = 'c3-eth0'
    ni.ifaddresses(MyETH0Iface)
    MyOwnIp = ni.ifaddresses(MyETH0Iface)[2][0]['addr']

    #Start the flesk app under public ip and default json port
    print 'Interface: %s, IPaddr: %s'%(MyETH0Iface, MyOwnIp)
    app.run(host=MyOwnIp, port=dconf.LBC_JsonPort)
