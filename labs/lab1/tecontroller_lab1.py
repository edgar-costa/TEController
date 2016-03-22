#!/usr/bin/python
from tecontroller.loadbalancer.simplepathlb import SimplePathLB
from tecontroller.linkmonitor.linksmonitor_thread import LinksMonitorThread
from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res import defaultconf as dconf
from tecontroller.res.problib import *
import threading
import time
import Queue

log = get_logger()
lineend = "-"*100+'\n'

class TEControllerLab1(SimplePathLB):
    def __init__(self):
        # Call init method from LBController
        super(TEControllerLab1, self).__init__()

        # Create lock for synchronization on accessing self.cg
        capacityGraphLock = threading.Lock()

        # Graph that will hold the link available capacities
        with capacityGraphLock:
            self.cg = self._createCapacitiesGraph()

        # Start the links monitorer thread linked to the event queue
        lmt = LinksMonitorThread(capacity_graph=self.cg, lock=capacityGraphLock)
        lmt.start()

        
    def run(self):
        """Main loop that deals with new incoming events
        """
        while not self.isStopped():
            # Get event from the queue (blocking)
            event = self.eventQueue.get()
                        
            if event['type'] == 'newFlowStarted':
                # Log it
                log.info(lineend)
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - run(): %s retrieved from eventQueue\n"%(t, event['type']))
                flow = event['data']
                log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))
                
                # Deal with new flow
                self.dealWithNewFlow(flow)
                
            else:
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - run(): UNKNOWN Event\n"%t)
                log.info("\t* Event: "%str(event))


    def dealWithNewFlow(self, flow):
        """
        Re-writes the parent class method.
        """
        # Get the communicating interfaces
        src_iface = flow['src']
        dst_iface = flow['dst']
                
        # Get host ip's
        src_ip = src_iface.ip
        dst_ip = dst_iface.ip
                
        # Get their correspoding networks
        src_network = src_iface.network
        dst_network = self.getCurrentOSPFPrefix(dst_iface.compressed)
                
        # Get the string-type prefixes
        src_prefix = src_network.compressed
        dst_prefix = dst_network.compressed
                
        # Get the current path from source to destination
        currentPaths = self.getActivePaths(src_iface, dst_iface, dst_prefix)
                
        # ECMP active?
        if len(currentPaths) > 1:
            # ECMP is happening
            ecmp_active = True
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): ECMP is ACTIVE\n"%t)
        elif len(currentPaths) == 1:
            # ECMP not active
            ecmp_active = False
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - dealWithNewFlow(): ECMP is NOT active\n"%t)
        else:
            t = time.strftime("%H:%M:%S", time.gmtime())
            to_log = "%s - dealWithNewFlow(): ERROR. No path between src and dst\n"
            log.info(to_log%t)
            return

        if ecmp_active:
            # Calculate congestion probability

            # Get active dag for current destination
            adag = self.getActiveDag(dst_prefix)
            
            # Insert current available capacities in dag
            for (u,v,data) in adag.edges(data=True).iteritems():
                cap = self.cg[u][v]['capacity']
                data['capacity'] = cap

            # Get ingress and egress router
            ingress_router = currentPaths[0][0]
            egress_router = currentPaths[0][-1]

            # compute congestion probability
            congProb = flowCongestionProbability(adag, ingress_router,
                                                 egress_router, flow.size)
            # Apply decision function
            # Act accordingly
            # Log it
            to_print = "\t* Flow will be allocated "
            to_print += "with a congestion probability of %f\n"
            log.info(to_print%congProb)
            to_print = "\t* Paths: %s\n"
            log.info(to_print%str([self.toLogRouterNames(path) for path in currentPaths]))

            # Allocate flow to current paths
            self.addAllocationEntry(dst_prefix, flow, currentPaths)

        else:
            # currentPath is still a list of a single list: [[A,B,C]]
            # but makes it more understandable
            currentPath = currentPaths

            # Can currentPath allocate flow w/o congestion?
            if self.canAllocateFlow(flow, currentPath):
                # No congestion. Do nothing
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - dealWithNewFlow(): Flow can be ALLOCATED\n"%t)

                # We just allocate the flow to the currentPath
                self.addAllocationEntry(dst_prefix, flow, currentPath)
            else:
                # Congestion created. 
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - dealWithNewFlow(): Flow will cause CONGESTION\n"%t)
                
                # Call the subclassed method to properly 
                # allocate flow to a congestion-free path
                self.flowAllocationAlgorithm(dst_prefix, flow, currentPath)

    def getMinCapacity(self, path):
        """
        We overwrite the method so that capacities are now checked from the
        SNMP couters data updated by the link monitor thread.
        """
        caps_in_path = []
        for (u,v) in zip(path[:-1], path[1:]):
            edge_data = self.cg.get_edge_data(u, v)
            cap = edge_data.get('capacity', None)
            caps_in_path.append(cap)
        try:
            mini = min(caps_in_path)
            return mini
        
        except ValueError:
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - getMinCapacity(): ERROR: min could not be calculated\n"%t)
            log.info("\t* Path: %s\n"%path)            
            raise ValueError

    def _createCapacitiesGraph(self):
        # Get copy of the network graph
        ng_copy = self.network_graph.copy()
        cg = self.network_graph.copy()
        
        for node in ng_copy.nodes_iter():
            if not ng_copy.is_router(node):
                cg.remove_node(node)
                
        for (x, y, edge_data) in cg.edges(data=True):
            edge_data['window'] = []
            edge_data['capacity'] = 0
        return cg


if __name__ == '__main__':
    log.info("LOAD BALANCER CONTROLLER - Lab 1 - Enforcing simple paths only\n")
    log.info("-"*60+"\n")
    time.sleep(dconf.LBC_InitialWaitingTime)
    
    tec = TEControllerLab1()
    tec.run()
                                
