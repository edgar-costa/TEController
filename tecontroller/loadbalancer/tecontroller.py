import Queue
import threading

from fibbingnode.algorithms.southbound_interface import SouthboundManager
from fibbingnode.misc.igp_graph import IGPGraph

from fibbingnode.misc.mininetlib.ipnet import TopologyDB
from fibbingnode import CFG

import networkx as nx

DB_path = '/tmp/db.topo'
C1_cfg = '/tmp/c1.cfg'

HAS_INITIAL_GRAPH = threading.Event()

class MyGraphProvider(SouthboundManager):

    def received_initial_graph(self):
        HAS_INITIAL_GRAPH.set()


        

class TEController(object):
    def __init__(self):
        """It basically reads the network topology from the MyGraphProvider,
        which is running in another thread because
        SouthboundManager.run() is blocking.
        
        Here we are assuming that the topology does not change.        
        """
        self.flow_allocation = {}
        self.eventQueue = Queue.Queue()
        self.timer = threading.Timer()
        self._stop = threading.Event()
        
        CFG.read(C1_cfg)
        db = TopologyDB(db=DB_path)
        sbmanager = MyGraphProvider(SouthboundManager)
        t = threading.Thread(target=sbmanager.run, name="Graph Listener")
        t.start()
        HAS_INITIAL_GRAPH.wait()
        self.network_graph = sbmanager.igp_graph

    def stop(self):
        """Stop the TEController correctly
        """
        self._stop.set()

    def isStopped(self):
        """Check if TEController is set to be stopped or not
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


class GreedyTEController(TEController):
    def __init__(self, *args, **kwargs):
        super(GreedyTEControllerLB, self).__init__(*args, **kwargs)

    



################
# Part of the controller that deals with new incoming flow demands
from flow import Flow

import flask 
app = flask.Flask(__name__)


@app.route("/newflowstarted", methods = ['POST'])
def newFlowStarted():
    req = flask.request.json

    flow = Flow(req['src'], req['dst'], req['sport'], req['dport'],
                req['size'], req['start_time'], req['duration'])

    queue = getQueue('TECQueue').getLock()
    queue.enqueue('newFlowStarted', flow)
    queue.release()

if __name__ == "__main__":
    #Should run under it's own IP!
    MyOwnIp = getMyOwnIp() 
    app.run(MyOwnIp)
