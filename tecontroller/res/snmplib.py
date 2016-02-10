"""This module implements the SnmpCounters class that helps dealing
with the SNMP data that we extract from the routers. Specifically,
keeps track of the interface counters.
"""

import numpy as np
import time
import subprocess
from pysnmp.hlapi import *

max_capacity = (100e6)/8

class SnmpCounters(object):
    def __init__(self, interfaces = ["2","3","4","5"], routerIp = "", port = 161):
        self.routerIp = routerIp
        self.port = port
        self.interfaces = interfaces
        self.countersTimeStamp  = time.time()
        self.counters = np.array([0]*len(self.interfaces))
        self.totalBytes = 0
        
    def getCounters32(self, direction='Out'):
        """This function should use pySnmp library instead. But due to a bug,
        we are using snmpwalk now.

        """
        if direction=='In':
            OID = 'ifInOctets'
        else:
            OID = 'ifOutOctets'

        p = subprocess.Popen(['snmpwalk',self.routerIp, OID],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate()

        ifaces_t = [a.split(" = ")[0] for a in out.split('\n') if len(a.split(" = ")) == 2]
        ifaces = [a[a.index('.')+1:] for a in ifaces_t if a]
        
        counters_t = [a.split(" = ")[1] for a in out.split('\n') if len(a.split(" = ")) == 2]
        counters = [a[a.index(':')+2:] for a in counters_t if a]

        return [(ifaces[i], counters[i]) for i in range(len(counters))]



    def link_capacity(self):
        link_capacity = self.countersDiff/(max_capacity*self.timeDiff)
        currentCapacity ={}
        for i,link in enumerate(self.interfaces):
            currentCapacity[link] = link_capacity[i]
        return currentCapacity
        
    def link_traffic(self):
        currentLoads ={}
        if self.totalBytes == 0:
            link_traffic =  np.array([0]*len(self.interfaces))
        else:
            link_traffic = self.countersDiff/self.totalBytes
            
        for i,link in enumerate(self.interfaces):
            currentLoads[link] = link_traffic[i]
        return currentLoads
                
                
    def fromLastLecture(self):
        return time.time() - self.countersTimeStamp

