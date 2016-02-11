"""This module implements the SnmpCounters class that helps dealing
with the SNMP data that we extract from the routers. Specifically,
keeps track of the interface counters.
"""
from pysnmp.hlapi import *
from tecontroller.res.flow import Base
import subprocess
import time
import datetime
import numpy as np

class SnmpCounters(Base):
    def __init__(self, routerIp = "127.0.0.1", port = 161):
        super(SnmpCounters, self).__init__()
        
        self.routerIp = routerIp
        self.port = port
        self.lastUpdated = 0
        self.interfaces = self.getInterfaces()
        self.counters = np.array([0]*len(self.interfaces))
        self.timeDiff = 0
        self.countersDiff = np.array([0]*len(self.interfaces))

        self.setRefreshTimeToMinimum()
        
    def __repr__(self):
        return "SNMPCounter(%s)"%self.routerIp

    def __str__(self):
        """
        """
        st = datetime.datetime.fromtimestamp(self.lastUpdated).strftime('%Y-%m-%d %H:%M:%S')
        s = "%s at %s:\n"%(self.routerIp, st)
        duration = self.timeDiff
        for i, data in enumerate(self.interfaces):
            mac = data['mac']
            bytes_observed = self.countersDiff[i]
            
            s += "    Iface Number: %s\tName: %s\tMAC: %s\tTraffic Observed: %s\tPeriod length: %s\n"%(data['number'],data['name'],mac, self.setSizeToStr2(bytes_observed), self.setTimeToStr(duration))
        return s


    
    def setRefreshTimeToMinimum(self):
        p = subprocess.Popen(['snmpset', self.routerIp, 'nsCacheTimeout.1.3.6.1.2.1.2.2', 'i', '1'],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate()


    
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
        
        ifaces_dict = [{'number': ifaces[i], 'mac':macs[i],
                        'name':names[i], 'mtu':mtus[i]} for i
                       in range(len(macs))]
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
        in_counters = np.asarray([int(a[a.index(':')+2:]) for a in in_counters_t if a][1:])
        
        # ifOutOctets
        # call snmpwalk
        p = subprocess.Popen(['snmpwalk', self.routerIp, 'ifOutOctets'],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        out, err = p.communicate()
        
        # process snmpwalk output
        out_counters_t = [a.split(" = ")[1] for a in out.split('\n') if len(a.split(" = ")) == 2]
        out_counters = np.asarray([int(a[a.index(':')+2:]) for a in out_counters_t if a][1:])

        # Treated as np.arrays from here on
        total_counters = np.multiply((in_counters + out_counters), 8) # in bits
        
        # update interfaces data structure
        updateTime=time.time()
        self.timeDiff = updateTime - self.lastUpdated
        self.countersDiff = total_counters - self.counters
        self.counters = total_counters
        
        # Update last timestamp
        self.lastUpdated = updateTime
        
    def fromLastLecture(self):
        return time.time() - self.lastUpdated


    def getLoads(self):
        """Returns the current loads of the router's interfaces
        """
        return self.countersDiff
    
    def getLoadByIfaceName(self, iface_name):
        """Return load of specific router interface. iface_name is assumed to
        be similar as: r1-eth0
        """
        load = [self.countersDiff[int(data['number'])-2] for data in
                self.interfaces if data['name'] == iface_name]
        if load != []:
            return load[0]
        else:
            raise KeyError("iface_name: %s does not belong to any router interface"%iface_name)

            
