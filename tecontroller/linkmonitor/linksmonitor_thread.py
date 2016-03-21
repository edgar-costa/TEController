from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res.snmplib import SnmpCounters
from tecontroller.res.dbhandler import DatabaseHandler
import threading
import time
import numpy as np

log = get_logger()

class LinksMonitorThread(threading.Thread):
    """
    This class defines a thread that will be spawned by the TEController 
    algorithm in order to periodically update the available capacities
    for the network links.
    """
    def __init__(self, queue, network_graph, interval=1.05):
        super(LinksMonitorThread, self).__init__()
        # Read network database
        self.db = DatabaseHandler()
    
        # Counters read interval
        self.interval = interval
    
        # Queue where to put the read results
        self.eventQueue = queue
        
        # Network IGPGraph. Only router-router links should be parsed
        self.ng = network_graph
        
        # Start router counters
        self.counters = self._startCounters()
        
        # Start router-to-router links
        self.links = self._startLinks()

    def run(self):
        while True:
            # Read capacities from SNMP
            self.updateLinksCapacities()
             
            # Push them to the eventQueue
            newCapacitiesUpdateEvent = {'type': 'newCapacitiesUpdate', 
                                         'data': self.links.copy()}
            self.eventQueue.put(newCapacitiesUpdateEvent)
            self.eventQueue.task_done()
              
            # Go to sleep interval time
            time.sleep(self.interval/2)
        
    def updateLinksCapacities(self):
        """
        """
        # Update counters first
        self._updateCounters()
        for router, counter in self.counters.iteritems():
            # Get router interfaces names
            iface_names = [data['name'] for data in counter.interfaces]
              
            # Get current loads for router interfaces 
            # (difference from last read-out)
            loads = counter.getLoads()
            # Get the time that has elapsed since last read-out
            elapsed_time = counter.timeDiff
            currentThroughputs = loads/float(elapsed_time)
              
            # Retrieve the bandwidths for router-connected links
            bandwidths = []
            for ifacename in iface_names:
                # Get bandwidth for link in that interface
                bw_tmp = [edge_data['bw'] for edge, edge_data in
                  self.links.iteritems() if edge_data['interface'] ==
                  ifacename]

                if bw_tmp != []:
                bandwidths.append(bw_tmp[0])

            bandwidths = np.asarray(bandwidths)
        
            # Calculate available capacities
            avialableCaps = bandwidths - currentThroughputs

            # Set link available capacities by interface name
            for i, iface_name in enumerate(iface_names):
                iface_availableCap = avialableCaps[i]
                self._setLinkCap(iface_name, iface_availableCap)
          
    def _updateCounters(self):
        """Updates all interface counters of the routers in the network.
        Blocks until the counters have been updated.
        """
        for r, counter in self.counters.iteritems():
            while (counter.fromLastLecture() < self.interval):
                pass
            counter.updateCounters32()

    def _setLinkCap(self, iface_name, capacity):
        edge = [edge for edge, data in self.links.iteritems() if
                data['interface'] == iface_name]
        if edge != []:
            (x,y) = edge[0]
            self.links[x][y]['capacity'] = capacity

    def _startCounters(self):
        """This function iterates the routers in the network and creates
        a dictionary mapping each router to a SnmpCounter object.
        
        Returns a dict: routerip -> SnmpCounters.
        """
        return {r:SnmpCounters(routerIp=r) for r in self.ng.routers()}

    def _startLinks(self):
        """
        Returns a dictionary:
        edge -> bw, load, interface
        set({x, y}) -> 
        
        Only router-to-router links are of interest (since we can't modify
        routes inside subnetworks).
        """
        return self.db.getAllRouterEdges()
