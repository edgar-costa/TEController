from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res.dbhandler import DatabaseHandler
from tecontroller.res import defaultconf as dconf
from tecontroller.res.flow import Flow
import ipaddress
import traceback
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

        # Data structure that maintains a set of current flows passing
        # through each router in the last second
        self.router_flowsets = {}
        self.updateRouterFlowSets()
            
    def run(self):
        """
        A dictionary of flow -> possible path list is read from the requestQueue.

        A dictionary indexed by flow -> allocated path is returned
        """
        queueLookupPeriod = 1 #seconds
        while True:
            try:
                requestFlowsDict = self.requestQueue.get(timeout=queueLookupPeriod) # Blocking read
            except:
                # Update flow sets for each router
                self.updateRouterFlowSets()
            else:
                responsePathDict = self.dealWithRequest(requestFlowsDict)
                if responsePathDict != {}:
                    self.responseQueue.put(responsePathDict)                    
                self.updateRouterFlowSets()

    def updateRouterFlowSets(self):
        for rid, capfile in self.capFilesDict.iteritems():
            lines = capfile.readlines()
            ridSet = set()
            for line in lines:
                try:
                    # Parse ip's 
                    src_tmp = line.split(' ')[2]
                    src_ip_tmp = src_tmp.split('.')[:4]
                    src_ip = ipaddress.ip_address('.'.join(map(str, src_ip_tmp)))
                    dst_tmp = line.split(' ')[4].strip(':')
                    dst_ip_tmp = dst_tmp.split('.')[:4]
                    dport = dst_tmp.split('.')[4]
                    dst_ip = ipaddress.ip_address('.'.join(map(str, dst_ip_tmp)))
                    ridSet.update({((src_ip, 's'), (dst_ip, 'd'), dport)})
                except:
                    #import ipdb; ipdb.set_trace()
                    #traceback.print_exception()
                    pass
                
            # Add set into dictionary
            self.router_flowsets[rid] = ridSet

    def dealWithRequest(self, requestFlowsDict):
        """
        """
        # Results are saved here
        responsePathDict = {}
        
        start_time = time.time()
        for f, pl in requestFlowsDict.iteritems():

            #flowsSet.update({(f.src, f.sport, f.dst, f.dport)})
            # We can't fix the source port from iperf client, so it
            # will never match. This implies that same host can't same
            # two UDP flows to the same destination host.
            flowSet = set()
            flowSet.update({((f.src.ip, 's'), (f.dst.ip, 'd'), str(f.dport))})
            
            # Set of routers containing flow
            routers_containing_flow = {self.db.getIpFromHostName(rid) for rid, rset in
                                       self.router_flowsets.iteritems() if
                                       rset.intersection(flowSet) != set()}
            
            # Iterate path list and choose which of them is the one in
            # which the flow is allocated
            pathSetList = [(p, set(p)) for p in pl]

            # Compute similarities with routers containing flows set
            pathCoincidences = [(p, pset, pset.intersection(routers_containing_flow),  
                                 len(pset.intersection(routers_containing_flow)))
                                for (p, pset) in pathSetList]

            # Get the one with biggest common routers
            (p, pset, prouters, similarity) = max(pathCoincidences, key=lambda x: x[3])

            # Only put in responsePathDict if all routers in which
            # flow was observed coincede with one of its possible
            # paths.
            if len(pset) == similarity:
                #import ipdb; ipdb.set_trace()
                responsePathDict[f] = p
            else:
                pass
            
        #log.info("*** It took %s seconds to compute which path should it go\n"%(time.time()-start_time))
        return responsePathDict

    
    def pickCapFiles(self):
        """
        Returns a dictionary indexed by router id -> corresponding .cap file
        """
        return {rid: open(dconf.CAP_Path+rid+'.cap', 'r') for rid in self.db.routers_to_ip.keys()}
        
            
