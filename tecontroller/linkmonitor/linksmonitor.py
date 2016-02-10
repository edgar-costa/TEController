"""This is a python script that will run in a dedicated mininet
host. This host will periodically monitor the load of all links in the
network and will log the corresponding data.

"""

from tecontroller.res.snmplib import SnmpCounters
from tecontroller.res.dbhandler import DatabaseHandler
import time

class LinksMonitor(DatabaseHandler):
    """
    Implements the class.
    """
    def __init__(self, interval):
        super(LinksMonitor, self).__init__()
        self.links = self._db_getAllEdges()
        self.interval = interval
        #self.counters = self.startCounters()
        
    def startCounters(self):
        routers = self._db_getRouters()
        self.counters = {name:'' for name, rid in routers}

        
if __name__ == '__main__':
    refreshInterval = 1
    lm = LinksMonitor(refreshInterval)
    
    import ipdb; ipdb.set_trace()
