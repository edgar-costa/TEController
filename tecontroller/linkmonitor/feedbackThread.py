from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res.dbhandler import DatabaseHandler
from tecontroller.res import defaultconf as dconf
from tecontroller.res.flow import Flow

import threading
import time

log = get_logger()

class feedbackThread(threading.Thread):
    """
    """
    def __init__(self, requestQueue, responseQueue):
        super(feedbackThread, self).__init__()

        # Create queue attributes
        self.requestQueue = requestQueue
        self.responseQueue = responseQueue

        # Read network database
        self.db = DatabaseHandler()

        # Fill router cap files
        self.capFilesDict = self.pickCapFiles()
        
    def run(self):
        """
        Tuples of (flow, possible path list) are read from the requestQueue.

        A dictionary indexed by flow -> allocated path is returned
        """
        
        while True:
            (nf, pl) = self.requestQueue.get() #blocking
            requestFlows = [(nf, pl)]
            while not self.requestQueue.empty():
                requestFlows.append(self.requestQueue.get())
                
            responsePathDict = self.dealWithRequest(requestFlows)
            self.responseQueue.put(responsePathDict)

    def dealWithRequest(self, requestFlows):
        """
        """
        # Read all .cap files from last time
        newReadOut = {}
        for rid, capfile in newReadOut.iteritems():
            newReadOut[rid] = capfile.readlines()

        # Create readOut flow sets
        readOutFlowSets = {}
        for rid, lines in newReadOut.iteritems():
            ridSet = set()
            
            
        # Create set of flows to look for in files
        flowsSet = set()
        for f, pl in requestedFlows:
            flowsSet.update({(f.src, f.sport, f.dst, f.dport)})

    def pickCapFiles(self):
        """
        Returns a dictionary indexed by router id -> corresponding .cap file
        """
        return {rid: open(dconf.CAP_Path+rid+'.cap', 'r') for rid in self.db.routers_to_ip.keys()}
        
            
