#!/usr/bin/python
"""This is a python script that will run in a dedicated mininet
host. This host will periodically monitor the load of all links in the
network and will log the corresponding data.

TODO:
 * Add logs to module
"""
from fibbingnode.misc.mininetlib import get_logger

from tecontroller.res.snmplib import SnmpCounters
from tecontroller.res.dbhandler import DatabaseHandler
from tecontroller.res import defaultconf as dconf

import time
import numpy as np

log = get_logger()
time_info = False

class LinksMonitor(object):
    """
    Implements the class.
    """
    def __init__(self, interval=1, logfile = dconf.LinksMonitor_LogFile):
        self.db = DatabaseHandler() 
        log.info("LINKS MONITOR -- interval: %s -- logfile: %s --\n"%(str(interval),logfile))
        log.info("-"*60+"\n")
        log.info("Read all edges from network...\n")
        self.links = self.db.getAllEdges()
        self.interval = interval
        log.info("Start all counters...\n")
        self.counters = self._startCounters()
        self.logfile = logfile
        log.info("%s\n"%self.printLinksToEdges())

    def printLinksToEdges(self):
        s = "Links to edges:\n"
        taken = []
        for link, data in self.links.iteritems():
            (x, y) = data['edge']
            if (x,y) in taken or (y,x) in taken:
                continue
            if not('r' in x and 'r' in y):
                continue
            taken.append((x,y))
            s += link+' -> '+str(data['edge'])+'\n'
        s += '\n\n'
        return s

    def printLinkToEdgesLine(self):
        s = ""
        taken = []
        for link, data in self.links.iteritems():
            (x, y) = data['edge']
            if (x,y) in taken or (y,x) in taken:
                continue
            taken.append((x,y))
            (x,y) = data['edge']
            s += link+'->(%s %s),'%(x,y)
        s += '\n'
        return s
    
    def __str__(self):
        s = ""
        taken = []
        for link, data in self.links.iteritems():
            (x, y) = data['edge']
            if (x,y) in taken or (y,x) in taken:
                continue
            taken.append((x,y))
            s += "%s %s -> load: (%.2f%%)\n"%(link, data['edge'], (100*data['load'])/data['bw'])
        s += '\n'
        return s    

    def _startCounters(self):
        start = time.time()
        routers = self.db.getRouters()
        counters_dict = {name:{'routerid':rid, 'counter': SnmpCounters(routerIp=rid)} for name, rid in routers}
        if time_info:
            log.info("linksmonitor.py: _startCounters() took %d seconds\n"%(time.time()-start))
        return counters_dict

    def _updateCounters(self):
        """Reads all counters of the routers in the network. Blocks until the
        counters have been updated.
        """
        start = time.time()
        for r, data in self.counters.iteritems():
            counter = data['counter']
            while (counter.fromLastLecture() < self.interval):
                pass
            counter.updateCounters32()
        if time_info:
            log.info("linksmonitor.py: _updateCounters() took %d seconds\n"%(time.time()-start))

    def _setLinkLoad(self, iface_name, load):
        name = [name for name, data in self.links.iteritems() if
                data['interface'] == iface_name]
        if name != []:
            name = name[0]
        self.links[name]['load'] = load
        
    def updateLinks(self):
        # Update the counters first
        start = time.time()
        self._updateCounters()
        #log.info("%s\n"%str(self.links))
        # Iterate the counters
        for name, data in self.counters.iteritems():
            # Get the counter object for each router
            counter = data['counter']
            # Get the router id for the counter
            routerid = counter.routerIp
            # Get ifaces name and load for each router interface
            iface_names = [data['name'] for data in counter.interfaces]
            loads = counter.getLoads()
            elapsed_time = counter.timeDiff

            bandwidths = []
            for ifacename in iface_names:
                bw_tmp= [data['bw'] for link, data in
                         self.links.iteritems() if data['interface']
                         == ifacename]
                if bw_tmp != []:
                    bandwidths.append(bw_tmp[0])
                    
            bandwidths = np.asarray(bandwidths)
            currentPercentages = np.multiply(loads/(np.multiply(bandwidths, elapsed_time)), 100)
            #log.info("Elapsed time: %s\n"%elapsed_time)
            #log.info("Loads: %s\n"%str(loads))
            #log.info("Bws: %s\n"%str(bandwidths))
            
            # Set link loads by interface name
            for i, iface_name in enumerate(iface_names):
                iface_load = currentPercentages[i]
                self._setLinkLoad(iface_name, iface_load)

        if time_info:
            log.info("linksmonitor.py: updateLinks() took %d seconds\n"%(time.time()-start))


    def log(self):
        """This function logs the state of the links. f is supposed to be an
        open python file with write access

        """
        f = open(self.logfile, 'a')
        s = "%s"%time.time()
        taken = []
        for link, data in self.links.iteritems():
            (x, y) = data['edge']
            if (x,y) in taken or (y,x) in taken:
                continue
            taken.append((x,y))
            load = data['load']
            s += ",(%s %.3f%%)"%(link, load)
        s += '\n'
        f.write(s)    
        f.close()

        
    def run(self):
        """
        """
        log.info("Going inside the run() loop...\n")
        # Write edges info to log file (first line)
        f = open(self.logfile, 'a')
        f.write(self.printLinkToEdgesLine())
        f.close()

        while True:
            # Update links with fresh data from the counters
            self.updateLinks()
            #log.info("Links updated...\n")

            # Log new values to logfile
            #log.info("Logging...\n")
            self.log()
            
            # Go to sleep for some interval time
            #log.info("Going to sleep...\n")
            time.sleep(self.interval/2)
                
if __name__ == '__main__':
    #Waiting for the IP's to be assigned...
    time.sleep(dconf.Hosts_InitialWaitingTime+5)
    
    refreshInterval = 1.05 #seconds
    try:
        f = open(dconf.LinksMonitor_LogFile, 'r')
    except IOError:
        f = open(dconf.LinksMonitor_LogFile, 'w')
        f.close()
    else:
        f = open(dconf.LinksMonitor_LogFile, 'w')
        f.close()
        
    lm = LinksMonitor(interval=refreshInterval)
    lm.run()

    
