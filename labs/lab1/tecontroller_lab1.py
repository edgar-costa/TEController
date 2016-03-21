from tecontroller.loadbalancer.simplepathlb import SimplePathLB
from fibbingnode.misc.mininetlib import get_logger

import Queue

log = get_logger()

class TEControllerLab1(SimplePathLB):
	def __init__(self):
		# Call init method from LBController
		super(TEControllerLab1, self).__init__()

		# Start the links monitorer thread linked to the event queue
		lmt = LinksMonitorerThread(queue = self.eventQueue,
							 	   network_graph = self.network_graph)
		lmt.start()

		# Graph that will hold the link available capacities
		self.cg = self._createCapacitiesGraph()

	def run(self):
		"""Main loop that deals with new incoming events
        """
        while not self.isStopped():
            # Get event from the queue (blocking)
            event = self.eventQueue.get()
            log.info(lineend)
            t = time.strftime("%H:%M:%S", time.gmtime())
            log.info("%s - run(): NEW event in the queue\n"%t)
            log.info("\t* Type: %s\n"%event['type'])
            
            if event['type'] == 'newFlowStarted':
                # Fetch flow from queue
                flow = event['data']
                log.info("\t* Flow: %s\n"%self.toLogFlowNames(flow))
                
                # Deal with new flow
                self.dealWithNewFlow(flow)

            elif event['type'] == 'newCapacitiesUpdate':
             	# Update the capacities graph
             	new_links_capacities = event['data']
             	self.updateCapacities(new_links_capacities)
             	
   	            t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - run(): network available capacities updated\n"%t)

            else:
                t = time.strftime("%H:%M:%S", time.gmtime())
                log.info("%s - run(): UNKNOWN Event\n"%t)
                log.info("\t* Event: "%str(event))

    def updateCapacities(self, new_links_capacities):
    	# update self.cg wrt new_capacities_graph
    	for (x,y), edge_data in new_links_capacities.iteritems():
    		window = self.cg[x][y]['window']
    		cap = self.cg[x][y]['cap']
    		if len(window) == 3: #median filter window size = 3
    			# Remove last element
	   			window.pop()

    		# Add new capacity readout to filter window
    		window = [edge_data['cap']] + window

    		# Perform the median filtering
    		# Sort them by magnitude
    		window_ordered = window[:]
    		window_ordered.sort()

    		# Take the median element
    		chosen_cap = window_ordered[len(window_ordered)/2] 

    		# Update edge data
    		self.cg[x][y]['window'] = window
    		self.cg[x][y]['cap'] = chosen_cap

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
        	# Apply decision function
        	# Act accordingly
        	pass

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
            cap = edge_data.get('cap', None)
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

		for (x, y, edge_data) in cg.edges(data=True).iteritems():
			edge_data['window'] = []
			edge_data['cap'] = 0

		return cg



