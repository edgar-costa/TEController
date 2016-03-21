
from fibbingnode.misc.mininetlib import get_logger
from tecontroller.res.snmplib import SnmpCounters
from tecontroller.res.dbhandler import DatabaseHandler
import threading
import time
import numpy as np

log = get_logger()

class LinksMonitorThread(threading.Thread):
	"""
	This class defines a thread that will be spawned by the TEController 
	algorithm in order to periodically update the available capacities
	for the network links.
	"""
	def __init__(self, interval=1.05, queue, network_graph):
    	    super(LinksMonitorThread, self).__init__()
    	    # Read network database
			self.db = DatabaseHandler()

    	    # Counters read interval
    	    self.interval = interval

    	    # Queue where to put the read results
        	self.eventQueue = queue

        	# Network IGPGraph. Only router-router links should be parsed
        	self.ng = network_graph

        	# Start router counters
        	self.counters = self._startCounters()

        	# Start router-to-router links
 			self.links = self._startLinks()

    def run(self):
    	while True:
    		# Read capacities from SNMP
    		new_cg = self.readCapacities()

    		# Push them to the eventQueue
    		newCapacitiesUpdateEvent = {'type': 'newCapacitiesUpdate', 'data': new_cg}
    		self.eventQueue.put(newCapacitiesUpdateEvent)
  		    self.eventQueue.task_done()
    	
    		# Go to sleep interval time
    		time.sleep(self.interval/2)

    def _startCounters(self):
	   	"""This function iterates the routers in the network and creates
	   	a dictionary mapping each router to a SnmpCounter object.

	   	Returns a dict: routerip -> SnmpCounters.
	   	"""
    	return {r:SnmpCounters(routerIp=r) for r in self.ng.routers()}

    def _startLinks(self):
    	"""
    	Returns a dictionary:
    		edge -> bw, load, interface
    		set({x, y}) -> 

    	Only router-to-router links are of interest (since we can't modify
    	routes inside subnetworks).
    	"""
    	all_edges = self.db.getAllRouterEdges()

    	pass

	def _updateCounters(self):
        """Updates all interface counters of the routers in the network.
        Blocks until the counters have been updated.
        """
        for r, counter in self.counters.iteritems():
            while (counter.fromLastLecture() < self.interval):
                pass
            counter.updateCounters32()
       