"""Subclasses IPRouter in order to spawn the SNMP Agent processes by
default in the mininet routers.
"""
from fibbingnode.misc.mininetlib.iprouter import IPRouter
from tecontroller.res import defaultconf as dconf

class MyCustomRouter(IPRouter):
    """Implements MyCustomRouter class.
    """
    def __init__(self, *args, **kwargs):
        super(MyCustomRouter, self).__init__(*args, **kwargs)
        
        # Spawn the command to start the snmpd process in the router
        self.cmd(dconf.START_SNMP_AGENT)
