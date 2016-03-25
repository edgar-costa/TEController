from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res.snmplib import SnmpCounters
from tecontroller.res.dbhandler import DatabaseHandler
from tecontroller.res import defaultconf as dconf

import threading
import time
import numpy as np

log = get_logger()


class LinksMonitorThread(threading.Thread):
    """This class defines a thread that will be spawned by the TEController 
    algorithm in order to periodically update the available capacities
    for the network links.

    It is passed a capacity graph and a lock from its parent, and it
    modifies it periodically.
    """
    def __init__(self, capacity_graph, lock, logfile, median_filter=False, interval=1.05):
        super(LinksMonitorThread, self).__init__()
        # Read network database
        self.db = DatabaseHandler()

        # Lock object to access capacity graph
        self.lock = lock

        # Counters read interval
        self.interval = interval

        # Capacity graph object
        self.cg = capacity_graph
        
        # Start router counters
        self.counters = self._startCounters()

        # Perform median filter or not?
        self.median_filter = median_filter
        
        # Start router-to-router links
        self.links = self._startLinks()

        # Used internally for the logs
        self.link_to_edge_bindings = self._createLinkToEdgeBindings()

        # Set log file
        if logfile:
            self.logfile = logfile
            # Write first line with links
            with open(self.logfile, 'w') as f:
                f.write(self.printLinkToEdgesLine(self.cg))
        else:
            self.logfile = None

    def _createLinkToEdgeBindings(self):
        bindings = {}
        taken = []
        i = 0
        for (u, v) in self.cg.edges():
            if (u, v) in taken or (v, u) in taken:
                continue
            else:
                taken.append((u,v))
                bindings[i] = (u, v)
                i = i + 1
        return bindings
            
    def run(self):
        while True:
            # Go to sleep interval time
            time.sleep(self.interval/2)

            # Read capacities from SNMP
            self.updateLinksCapacities()

            # Log them in the log file too
            if self.logfile:
                self.logLinksLoads()
            
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
                          self.links.iteritems() if
                          edge_data['interface'] == ifacename]

                if bw_tmp != []:
                    bandwidths.append(bw_tmp[0])
                else:
                    bandwidths.append(0)
                                        
            # Convert as a numpy array
            bandwidths = np.asarray(bandwidths)

            # Calculate available capacities
            availableCaps = bandwidths - currentThroughputs

            # Set link available capacities by interface name
            # Get lock first
            for i, iface_name in enumerate(iface_names):
                iface_availableCap = availableCaps[i]
                self.updateLinkCapacity(iface_name, iface_availableCap)

    def logLinksLoads(self):
        # Make a copy of the self.cg and release the lock
        with self.lock:
            cg_copy = self.cg.copy()
            
        with open(self.logfile, 'a') as f:
            s = "%s"%time.time()
            to_iterate = sorted(self.link_to_edge_bindings.keys())
            for index in to_iterate:
                (x,y) = self.link_to_edge_bindings[index]
                link_index = index
                availableCapactiy = cg_copy[x][y]['capacity']
                bandwidth = cg_copy[x][y]['bw']
                usedCapacity = bandwidth - availableCapactiy
                load = (usedCapacity/float(bandwidth))*100.0
                s += ",(L%d %.3f%%)"%(link_index, load)
            s += '\n'
            f.write(s)
           
    def _updateCounters(self):
        """Updates all interface counters of the routers in the network.
        Blocks until the counters have been updated.
        """
        for r, counter in self.counters.iteritems():
            while (counter.fromLastLecture() < self.interval):
                pass
            counter.updateCounters32()

    def updateLinkCapacity(self, iface_name, new_capacity):
        # Get nodes from the link with such iface_name
        edge = [edge for edge, data in self.links.iteritems() if
                data['interface'] == iface_name]
        if edge != []:
            (x, y) = edge[0]
        else:
            return
        
        with self.lock:
            if self.median_filter == True:
                # Perform median filter of window size = 3
                window = self.cg[x][y]['window']
                cap = self.cg[x][y]['capacity']
                
                if len(window) == 3: #median filter window size = 3
                    # Remove last element
                    window.pop()

                # Add new capacity readout to filter window
                window = [new_capacity] + window

                # Perform the median filtering
                # Sort them by magnitude
                window_ordered = window[:]
                window_ordered.sort()

                # Take the median element
                chosen_cap = window_ordered[len(window_ordered)/2] 

                # Update edge data
                self.cg[x][y]['window'] = window
                self.cg[x][y]['capacity'] = chosen_cap
        
            else:
                # No median filter
                self.cg[x][y]['capacity'] = new_capacity

                
    def updateCapacities(self, new_links_capacities):
        # update self.cg wrt new_capacities_graph
        for (x,y), edge_data in new_links_capacities.iteritems():
            x_ip = self.db.routerid(x)
            y_ip = self.db.routerid(y)
        
    def printLinkToEdgesLine(self, capacity_graph):
        s = ""
        to_iterate = sorted(self.link_to_edge_bindings.keys())
        for index in to_iterate:
            (x,y) = self.link_to_edge_bindings[index]
            link_number = index
            x_name = self.db.getNameFromIP(x)
            y_name = self.db.getNameFromIP(y)
            s += ("L%d"%link_number)+'->(%s %s),'%(x_name, y_name)
        s += '\n'
        return s
            
    def _startCounters(self):
        """This function iterates the routers in the network and creates
        a dictionary mapping each router to a SnmpCounter object.
        
        Returns a dict: routerip -> SnmpCounters.
        """
        with self.lock:
            counters_dict = {r:SnmpCounters(routerIp=r) for r in self.cg.routers}
        return counters_dict
    
    def _startLinks(self):
        """
        Returns a dictionary:
        edge -> bw, load, interface
        set({x, y}) -> 
        
        Only router-to-router links are of interest (since we can't modify
        routes inside subnetworks).
        """
        return self.db.getAllRouterEdges()

    
