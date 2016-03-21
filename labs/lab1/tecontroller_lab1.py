from tecontroller.loadbalancer.lbcontroller import LBController
from fibbingnode.misc.mininetlib import get_logger

log = get_logger()

class TEControllerLab1(LBController):
	def __init__(self):
		# Call init method from LBController
		super(TEControllerLab1, self).__init__()

		# Now do extra stuff here (like spawning the link monitor)

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
	        	
	        	# We just allocate the flow to the currentPaths
    	    	self.addAllocationEntry(dst_prefix, flow, currentPath)