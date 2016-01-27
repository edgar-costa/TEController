"""
This module defines the flow object
"""

from tecontroller.res import defaultconf as dconf
import requests


class Base(object):
    """
    Base class
    """
    def __init__(self, *args, **kwargs):
        pass
        
    def setSizeToInt(self, size):
        """" Converts the sizes string notation to the corresponding integer
        (in bytes).  Input size can be given with the following
        magnitudes: B, K, M and G.

        """
        if isinstance(size, int):
            return size
        try:
            int(size)
        except:
            conversions = {'B': 1, 'K': 1e3, 'M': 1e6, 'G': 1e9}
            digits_list = range(48,58)
            magnitude = chr(sum([ord(x) if (ord(x) not in digits_list)
                                 else 0 for x in size]))
            digit = int(size[0:(size.index(magnitude))])
            magnitude = conversions[magnitude]
            return int(magnitude*digit)
        else:
            return int(size)

        
    def setSizeToStr(self, size):
        """Expects an integer representing number of bytes as input.
        """
        #units = [('G', 1e9), ('M', 1e6), ('K', 1e3), ('B', 1)]
        units = [('M', 1e6), ('K', 1e3)] #only K and M are supported by iperf
        string = "%.3f"
        for (unit, value) in units:
            q, r = divmod(size, value)
            if q > 0.0:
                val = (q*value + r)/value 
                string = string % val
                string = string + unit
                return string
            
    def setTimeToInt(self, duration = '1m'):
        """Transforms the time notation into an integer representing the time
        in seconds. The time notation can mean either duration of the
        flow or starting time with regard to the trafficGenerator
        starting time.

        If given as string, m define minutes and s seconds. Example:
        1m30s would give 90 as output.

        It can also be given as the integer or just a string without m
        or s, which would represent the time in seconds.

        """
        if isinstance(duration, int):
            return duration
        try:
            int(duration)
        except:
            minutes = 0
            seconds = 0
            m = duration.find('m')
            if m != -1:
                minutes = duration.split('m')[0]
                duration = duration[m:]
            if duration.find('s') != -1:
                seconds = duration.split('s')[0]
            return int(minutes)*60 + int(seconds)            
        else:
            return int(duration)

    def setTimeToStr(self, time):
        """Expects time in seconds as integer.
        """
        m, s = divmod(time, 60)
        return "%dm%ds"%(m,s)
    

class Flow(Base):
    """
    This class implements a flow object.
    """
    def __init__(self, src = "0.0.0.0", dst = "0.0.0.0", sport = '5001',
                 dport = '5001', size = 1, start_time = '10s',
                 duration = '1m', *args, **kwargs):
        super(Flow, self).__init__(*args, **kwargs)
        self.src = src
        self.dst = dst
        self.sport = sport
        self.dport = dport
        self.size = self.setSizeToInt(size)
        self.start_time = self.setTimeToInt(start_time)
        self.duration = self.setTimeToInt(duration)

    def __repr__(self):
        a = "Src: %s:%s, Dst: %s:%s, Size: %s, Start_time: %s, Duration: %s" 
        return a%(self.src, self.sport, self.dst, self.dport,
                  self.size, self.setTimeToStr(self.start_time),
                  self.setTimeToStr(self.duration))

    def __setitem__(self, key, value):
        if key not in ['src','dst','sport','dport','size','start_time','duration']:
            raise Error
        else:
            self.__setattr__(key, value)

    def __getitem__(self, key):
        if key not in ['src','dst','sport','dport','size','start_time','duration']:
            raise Error
        else:
            return self.__getattribute__(key)
        
    def toJSON(self):
        """Returns the JSON-REST string that identifies this flow
        """
        flow = {"src": self.src, "dst": self.dst, "sport":
                self.sport, "dport": self.dport, "size": self.size,
                "start_time": self.start_time, "duration": self.duration}
        return flow


    def informCustomDaemon(self, ip):
        """This method is only useful for testing !!! Normally the method
        under TrafficGenerator should be used instead.

        Part of the code that deals with the JSON interface to inform to
        LBController a new flow created in the network.

        """
        url = "http://%s:%s/startflow" %(ip, dconf.LBC_JsonPort)
        #log.info("URL OF Flow.informCustomDaemonu: %s\n"%url)
        requests.post(url, json = self.toJSON())

