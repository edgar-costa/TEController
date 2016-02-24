#!/usr/bin/python

from tecontroller.loadbalancer.lbcontroller import LBController
from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res import defaultconf as dconf

import networkx as nx

class ECMPLB(LBController):
    """
    """
    def __init__(self, *args, **kwargs):
        super(ECMPLBController, self).__init__(*args, **kwargs)

    def dealWithNewFlow(self, flow):
        """
        Implements abstract method.
        """
        pass

if __name__ == '__main__':
    log.info("ECMP-AWARE LOAD BALANCER CONTROLLER\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    lb = ECMPLB()
    lb.run()
