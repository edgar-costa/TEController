"""Subclasses IPRouter in order to spawn the SNMP Agent processes by
default in the mininet routers.
"""
from fibbingnode.misc.mininetlib.iprouter import IPRouter
from tecontroller.res import defaultconf as dconf
from subprocess import Popen, PIPE
import time
import threading

from fibbingnode.misc.mininetlib import get_logger

log = get_logger()

class MyCustomRouter(IPRouter):
    """Implements MyCustomRouter class.
    """
    def __init__(self, *args, **kwargs):
        super(MyCustomRouter, self).__init__(*args, **kwargs)
        # Spawn the command to start the snmpd process in the router
        self.cmd(dconf.START_SNMP_AGENT)
        
        # Create process that will write in the .cap file
        self.feedback_id = self.router.id
        
    def start(self):
        super(MyCustomRouter, self).start()

        # Call separate thread
        router_filename = dconf.CAP_Path+self.feedback_id+'.cap'
        router_file = open(router_filename, 'w')
        p = self.popen(['tcpdump', '-n', '(udp','and','not','port','161)', '-i', 'any'], stdout=router_file, stderr=PIPE)
