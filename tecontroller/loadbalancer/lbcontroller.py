#!/usr/bin/python

"""Implements a flow-based load balancer using Fibbing. 

Is built upon the Northbound controller, and balances the load of the
network in terms of forwarding DAGs between source-destination pairs.

Receives flow demands from the custom built Traffic Generator, through
a Json-Rest interface.

"""

from fibbingnode.algorithms.southbound_interface import SouthboundManager
from fibbingnode.misc.igp_graph import IGPGraph

from fibbingnode.misc.mininetlib.ipnet import TopologyDB
from fibbingnode import CFG

from tecontroller.res import defaultconf as dconf

import networkx as nx
import threading
import subprocess

import shared

HAS_INITIAL_GRAPH = threading.Event()

lbcontroller_logfile = dconf.Hosts_LogFolder + "LBC_json.log"


class MyGraphProvider(SouthboundManager):
    """This class overrwides the received_initial_graph abstract method of
    the SouthboundManager class. It is used to receive the initial
    graph from the Fibbing controller.

    The HAS_INITIAL_GRAPH is set when the method is called.

    """
    def received_initial_graph(self):
        HAS_INITIAL_GRAPH.set()        


        
class LBController(object):
    def __init__(self):
        """It basically reads the network topology from the MyGraphProvider,
        which is running in another thread because
        SouthboundManager.run() is blocking.
        
        Here we are assuming that the topology does not change.        
        """
        self.flow_allocation = {}
        self.eventQueue = shared.eventQueue #From where to read events 
        self.timer_handlers = [] #threading.Timer() #Used to schedule flow alloc. removals
        self._stop = threading.Event() #Used to stop the thread

        CFG.read(dconf.C1_Cfg) #Must be called before create instance
                               #of SouthboundManager
        db = TopologyDB(db=dconf.DB_Path)

        sbmanager = MyGraphProvider()
        t = threading.Thread(target=sbmanager.run, name="Graph Listener")
        t.start()
        HAS_INITIAL_GRAPH.wait() #Blocks until initial graph arrives
        self.network_graph = sbmanager.igp_graph

        #spawn Json listener thread
        #lbc_lf = open(lbcontroller_logfile, 'w')
        #subprocess.Popen(['./jsonlistener.py'], stdin=None,
        #                 stdout=lbc_lf, stderr=lbc_lf)
        #lbc_lf.close()

        import ipdb; ipdb.set_trace() #SET TRACEEEEEEEEEEEEEEEEEEEEEEEEE
        
    def stop(self):
        """Stop the LBController correctly
        """
        #Here we should deal with the handlers of the spawned threads
        #and subprocesses...
        self._stop.set()

    def isStopped(self):
        """Check if LBController is set to be stopped or not
        """
        return self._stop.isSet()

    def run():
        """Main loop that deals with new incoming events
        """
        while not self.isStopped():
            
            #Wait until there's something in the queue
            while self.eventQueue.empty(): 
                pass
        
            event = self.eventQueue.get() #Should be blocking?
            if event['type'] == 'newFlowStarted':
                flow = event['data']
                self.dealWithNewFlow(flow, algorithm='greedy')
            else:
                print event

                
    def assignFlowToPath(self, flow, path):
        pass

    def removeFlowFromPath(self, flow, path):
        pass

    def deletePathFromGraph(self, path):
        pass
    
    def dealWithNewFlow(self, flow):
        currentPath = self.getCurrentPath(flow.src, flow.dst)
        if self.canAllocateFlow(currentPath, flow):
            updateFlowAllocationTable(currentPath, flow)
        else:
            path = self.getNewCongestionFreePath(flow)            

    def getCurrentPath(self, src, dst):
        """Gives the current path from src to dest
        """
        pass

    def canAllocateFlow(self, path, flow):
        """Returns true if there is at least flow.size bandwidth available in
        all links along the path from flow.src to src.dst,

        """
        pass
    
    def updateFlowAllocationTable(path, flow):
        if path in self.flow_allocation.keys():
            self.flow_allocation[path].append(flow)
        else:
            self.flow_allocation[path] = [flow]

            
class GreedyLBController(LBController):
    def __init__(self, *args, **kwargs):
        super(GreedyLBControllerLB, self).__init__(*args, **kwargs)

    



