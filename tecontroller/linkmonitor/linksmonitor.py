"""This is a python script that will run in a dedicated mininet
host. This host will periodically monitor the load of all links in the
network and will log the corresponding data.

"""
from tecontroller.res.snmplib import SnmpCounters
from tecontroller.res.dbhandler import DatabaseHandler
from tecontroller.res import defaultconf as dconf
import time

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
        action = [data['counter'].updateCounters32() for r, data in self.counters.iteritems()]

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
            tmp = [(data['name'], data['load_last_period']) for mac,
                   data in counter.interfaces.iteritems()]
            # Set link loads by interface name
            tmp2 = [self._setLinkLoad(iface_name, load) for
                    iface_name, load in tmp]


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
            bw = data['bw']
            elapsed_time = self.interval
            percent = 100*(load/(bw*elapsed_time))
            s += ",(%s,%.2f%%)"%(link, percent)
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
            print "Links updated"
            
            # Log new values to logfile
            self.log(f)
            print "Links logged"

            # Go to sleep for some interval time
            print "Going to sleep"
            time.sleep(self.interval)
            
                
        
if __name__ == '__main__':
    refreshInterval = 3 #second
    lm = LinksMonitor(interval=refreshInterval)
    lm.printLinksToEdges()
    lm.run()


    
