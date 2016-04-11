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
        A dictionary of flow -> possible path list is read from the requestQueue.

        A dictionary indexed by flow -> allocated path is returned
        """        
        while True:
            requestFlowsDict = self.requestQueue.get() # Blocking read
            responsePathDict = self.dealWithRequest(requestFlows)
            self.responseQueue.put(responsePathDict)

    def dealWithRequest(self, requestFlowsDict):
        """
        """
        # Results are saved here
        responsePathDict = {}
        
        # Read all .cap files from last time
        newReadOut = {}
        for rid, capfile in newReadOut.iteritems():
            newReadOut[rid] = capfile.readlines()

        # Create readOut flow sets
        readOutFlowSets = {}
        for rid, lines in newReadOut.iteritems():
            ridSet = set()
            for line in lines:
                try:
                    # Parse ip's 
                    src_tmp = line.split(' ')[2]
                    src_ip_tmp = src_tmp.split('.')[:4]
                    src_ip = ipaddress.ip_address('.'.join(map(str, src_ip_tmp)))
                    dst_tmp = line.split(' ')[2].strip(':')
                    dst_ip_tmp = dst_tmp.split('.')[:4]
                    dport = dst_tmp.splot('.')[4]
                    dst_ip = ipaddress.ip_address('.'.join(map(str, dst_ip_tmp)))
                    ridSet.update({(src_ip, dst_ip, dport)})
                except:
                    import ipdb; ipdb.set_trace()
                    pass
                
            # Add set into dictionary
            readOutFlowSets[rid] = ridSet
            
        for f, pl in requestFlowsDict.iteritems():
            #flowsSet.update({(f.src, f.sport, f.dst, f.dport)})
            # We can't fix the source port from iperf client, so it
            # will never match. This implies that same host can't same
            # two UDP flows to the same destination host.
            flowSet = set()
            flowSet.update({(f.src, f.dst, f.dport)})
            
            # Set of routers containing flow
            routers_containing_flow = {rid for rid, rset in
                                       readOutFlowSets.iteritems() if
                                       rset.intersection(flowSet) != set()}
            
            # Iterate path list and choose which of them is the one in
            # which the flow is allocated
            pathSetList = [(p, set(p)) for p in pl]

            # Compute similarities with routers containing flows set
            pathCoincidences = [(p, pset,
                                 len(pset.intersection(routers_containing_flows)))
                                for (p, pset) in pathSetList]

            # Get the one with biggest common routers
            (p, pset, similarity) = max(pathCoincidences, key=lambda x: x[2])

            # Only put in responsePathDict if all routers in which
            # flow was observed coincede with one of its possible
            # paths.
            if len(pset) == similarity:
                responsePathDict[f] = p

            else:
                # No full path found for this flow yet!
                pass
            
        return responsePathDict

    
    def pickCapFiles(self):
        """
        Returns a dictionary indexed by router id -> corresponding .cap file
        """
        return {rid: open(dconf.CAP_Path+rid+'.cap', 'r') for rid in self.db.routers_to_ip.keys()}
        
            
