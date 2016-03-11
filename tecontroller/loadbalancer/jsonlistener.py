"""This script is intended to be spawned as an independent thread by tecontroller.

It basically listens for information sent by the traffic generator
through a flesk interface.

Upon receiving a new flow notificaiton, puts the event inside the
shared queue eventQueue.
"""
from tecontroller.res.flow import Flow
from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res import defaultconf as dconf
import netifaces as ni
import time
import threading

import flask 

log = get_logger()

class JsonListener(threading.Thread):
    def __init__(self, queue):
        super(JsonListener, self).__init__()
        self.eventQueue = queue
        self.app = flask.Flask(__name__)
        self.app.add_url_rule("/newflowstarted",
                              'self.newFlowStarted', self.newFlowStarted, methods =
                              ['POST'])
        
    def run(self):
        #Searching for the interface's IP addr
        MyETH0Iface = 'c3-eth0'
        ni.ifaddresses(MyETH0Iface)
        MyOwnIp = ni.ifaddresses(MyETH0Iface)[2][0]['addr']
                
        #Start the flesk app under public ip and default json port
        log.info('LBC JSON LISTENER - HOST %s - IFACE %s\n'%(MyOwnIp, MyETH0Iface))
        log.info("-"*60+"\n")
        self.app.run(host=MyOwnIp, port=dconf.LBC_JsonPort)    

    def newFlowStarted(self):
        req = flask.request.json
        flow = Flow(req['src'], req['dst'], req['sport'], req['dport'],
                    req['size'], req['start_time'], req['duration'])
        
        newFlowStartedEvent = {'type': 'newFlowStarted', 'data': flow}

        self.eventQueue.put(newFlowStartedEvent)
        self.eventQueue.task_done()
        
