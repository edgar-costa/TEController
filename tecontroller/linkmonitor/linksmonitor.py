"""This is a python script that will run in a dedicated mininet
host. This host will periodically monitor the load of all links in the
network and will log the corresponding data.

"""
from tecontroller.res.snmplib import SnmpCounters
from tecontroller.res.dbhandler import DatabaseHandler
from tecontroller.res import defaultconf as dconf
import time
import numpy as np

class LinksMonitor(DatabaseHandler):
    """
    Implements the class.
    """
    def __init__(self, interval=1, logfile = dconf.LinksMonitor_LogFile):
        super(LinksMonitor, self).__init__()
        self.links = self._db_getAllEdges()
        self.interval = interval
        self.counters = self._startCounters()
        self.logfile = logfile

    def printLinksToEdges(self):
        s = "Links to edges\n==============\n"
        taken = []
        for link, data in self.links.iteritems():
            (x, y) = data['edge']
            if (x,y) in taken or (y,x) in taken:
                continue
            taken.append((x,y))
            s += link+' -> '+str(data['edge'])+'\n'
        s += '\n\n'
        print s

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
        routers = self._db_getRouters()
        counters_dict = {name:{'routerid':rid, 'counter': SnmpCounters(routerIp=rid)} for name, rid in routers}
        return counters_dict

    def _updateCounters(self):
        """Reads all counters of the routers in the network. Blocks until the
        counters have been updated.
        """
        for r, data in self.counters.iteritems():
            counter = data['counter']
            while (counter.fromLastLecture() < self.interval):
                pass
            counter.updateCounters32()  

    def _setLinkLoad(self, iface_name, load):
        name = [name for name, data in self.links.iteritems() if
                data['interface'] == iface_name]
        if name != []:
            name = name[0]
        self.links[name]['load'] = load

        
    def updateLinks(self):
        # Update the counters first
        self._updateCounters()

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


            print "Elapsed time: %s"%elapsed_time
            print "Loads: %s"%str(loads)
            print "Bws: %s"%str(bandwidths)
            
            # Set link loads by interface name
            for i, iface_name in enumerate(iface_names):
                iface_load = currentPercentages[i]
                self._setLinkLoad(iface_name, iface_load)

    def log(self, f):
        """This function logs the state of the links. f is supposed to be an
        open python file with write access

        """
        s = "%s"%time.time()
        taken = []
        for link, data in self.links.iteritems():
            (x, y) = data['edge']
            if (x,y) in taken or (y,x) in taken:
                continue
            taken.append((x,y))
            load = data['load']
            s += ",(%s,%.2f%%)"%(link, load)
        s += '\n'
        print s
        f.write(s)    

            
    def run(self):
        """
        """
        f = open(self.logfile, 'w')
        
        while True:
            # Update links with fresh data from the counters
            self.updateLinks()
            # Log new values to logfile
            self.log(f)
            # Go to sleep for some interval time
            time.sleep(self.interval/2)
                
if __name__ == '__main__':
    refreshInterval = 1.05 #seconds
    lm = LinksMonitor(interval=refreshInterval)
    lm.printLinksToEdges()
    lm.run()


    
