"""This module implements the SnmpCounters class that helps dealing
with the SNMP data that we extract from the routers. Specifically,
keeps track of the interface counters.
"""
from pysnmp.hlapi import *
from tecontroller.res.flow import Base
import subprocess
import time
import datetime


max_capacity = (100e6)/8

class SnmpCounters(Base):
    def __init__(self, routerIp = "127.0.0.1", port = 161):
        super(SnmpCounters, self).__init__()
        
        self.routerIp = routerIp
        self.port = port
        self.lastUpdated = time.time()
        self.interfaces = self.getInterfaces()
        # set counters to initial state
        self.updateCounters32()

    def __repr__(self):
        return "SNMPCounter(%s)"%self.routerIp

    def __str__(self):
        st = datetime.datetime.fromtimestamp(self.lastUpdated).strftime('%Y-%m-%d %H:%M:%S')
        s = "%s at %s:\n"%(self.routerIp, st)
        for mac, data in self.interfaces.iteritems():
            duration = data['duration_last_period']
            bytes_observed = data['load_last_period']
            avg_usage = int(bytes_observed/float(duration))
            
            s += "    Iface Number: %s  Name: %s\tMAC: %s\tTotal: %s\tPeriod length: %s\tAvg.Usage: %s/s\n"%(data['number'],data['name'],mac, self.setSizeToStr2(bytes_observed), self.setTimeToStr(duration), self.setSizeToStr2(avg_usage))
        return s


    def getLoadByIfaceName(self, iface_name):
        loads = [data['load'] for mac, data in self.interfaces.iteritems() if data['name'] == iface_name]
        if loads != []:
            load = loads[0]
            return load
        else:
            raise KeyError("iface_name: %s does not belong to any router interface"%iface_name)

            
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
                                'mtu':mtus[i], 'load_last_period': 0,
                                'duration_last_period':0, 'total':0}
                       for i in range(len(macs))}
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
        updateTime=time.time()

        for (num, i, o) in data:
            mac = [mac for mac, data in self.interfaces.iteritems() if data['number'] == num][0]
            
            total_bytes = self.interfaces[mac]['total']
            previous_load = self.interfaces[mac]['load_last_period']

            sumio = int(i) + int(o)
            difference = sumio - total_bytes

            if difference != 0:
                # Counters have been updated, so change data
                self.interfaces[mac]['total'] += difference
                self.interfaces[mac]['load_last_period'] = difference
                self.interfaces[mac]['duration_last_period'] = updateTime - self.lastUpdated
                
                # Update last timestamp
                self.lastUpdated = updateTime
            else:
                # Counters haven't been updated
                break

        
    def fromLastLecture(self):
        return time.time() - self.lastUpdated

