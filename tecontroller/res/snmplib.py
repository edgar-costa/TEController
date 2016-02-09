"""
"""
import numpy as np
import time

class SnmpCounters(object):
    def __init__(self, interfaces = ["2","3","4","5"], routerIp = "1.0.9.2", port = 161):
        self.routerIp = routerIp
        self.port = port
        self.interfaces = interfaces
        self.countersTimeStamp  = time.time()
        self.counters = np.array([0]*len(interfaces))
        self.totalBytes = 0
        
