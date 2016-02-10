"""This module implements the SnmpCounters class that helps dealing
with the SNMP data that we extract from the routers. Specifically,
keeps track of the interface counters.
"""
from pysnmp.hlapi import *
import subprocess
import time

max_capacity = (100e6)/8

class SnmpCounters(object):
    def __init__(self, routerIp = "", port = 161):
        self.routerIp = routerIp
        self.port = port
        self.lastUpdated = time.time()
        self.interfaces = self.getInterfaces()
        # set counters to initial state
        self.updateCounters32()

    def getInterfaces(self):
        """
        """
        # get the interface names
        OID = 'ifDescr'
        p = subprocess.Popen(['snmpwalk',self.routerIp, OID],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate()
        names_t = [a.split(" = ")[1] for a in out.split('\n') if
                  len(a.split(" = ")) == 2 and out.split('\n').index(a) != 0]
        names = [a[a.index(':')+2:] for a in names_t if a]

        # get the mtus
        OID = 'ifMtu'
        p = subprocess.Popen(['snmpwalk',self.routerIp, OID],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate()
        mtus_t = [a.split(" = ")[1] for a in out.split('\n') if
                  len(a.split(" = ")) == 2 and out.split('\n').index(a) != 0]
        mtus = [int(a[a.index(':')+2:]) for a in mtus_t if a]

        # then the physical addresses
        OID = "ifPhysAddress"
        p = subprocess.Popen(['snmpwalk',self.routerIp, OID],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate()
        ifaces_t = [a.split(" = ")[0] for a in out.split('\n') if
                    len(a.split(" = ")) == 2 and out.split('\n').index(a) != 0]
        ifaces = [a[a.index('.')+1:] for a in ifaces_t if a]

        macs_t = [a.split(" = ")[1] for a in out.split('\n') if
                  len(a.split(" = ")) == 2 and out.split('\n').index(a) != 0]
        macs = [a[a.index(':')+2:] for a in macs_t if a]
        
        ifaces_dict = {macs[i]:{'number': ifaces[i], 'name':names[i],
                                'out':0, 'in':0, 'mtu':mtus[i], 'load':0} for i in range(len(macs))}
        return ifaces_dict

    
    def updateCounters32(self):
        """This function should use pySnmp library instead. But due to a bug,
        we are using snmpwalk now.
        """
        # ifInOctets
        # call snmpwalk
        p = subprocess.Popen(['snmpwalk', self.routerIp, 'ifInOctets'],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate()
        
        # process snmpwalk output
        numbers_t = [a.split(" = ")[0] for a in out.split('\n') if len(a.split(" = ")) == 2]
        numbers = [a[a.index('.')+1:] for a in numbers_t if a][1:]
        
        in_counters_t = [a.split(" = ")[1] for a in out.split('\n') if len(a.split(" = ")) == 2]
        in_counters = [a[a.index(':')+2:] for a in in_counters_t if a][1:]
        
        # ifOutOctets
        # call snmpwalk
        p = subprocess.Popen(['snmpwalk', self.routerIp, 'ifOutOctets'],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate()
        
        # process snmpwalk output
        out_counters_t = [a.split(" = ")[1] for a in out.split('\n') if len(a.split(" = ")) == 2]
        out_counters = [a[a.index(':')+2:] for a in out_counters_t if a][1:]

        data = [(numbers[i], in_counters[i], out_counters[i]) for i in range(len(out_counters))]

        # update interfaces data structure
        for (num, i, o) in data:
            mac = [mac for mac, data in self.interfaces.iteritems() if data['number'] == num][0]
            #import ipdb; ipdb.set_trace();
            old_load = self.interfaces[mac]['load']
            self.interfaces[mac]['load'] = (int(i) + int(o)) - old_load
            self.interfaces[mac]['in'] = int(i)
            self.interfaces[mac]['out'] = int(o)            
            
        # update last timestamp
        self.lastUpdated = time.time()

        
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

