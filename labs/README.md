# Explanation of the TEController algorithms

## General assumptions

1. The flow demands are known to the TEC. The traffic generator
   informs the TEC every time there is a new flow starting on the
   network. This is essential, since we know which prefix we have to
   fib.

2. The link utilization is, at the moment, a link data attribute that
   is self-maintained by the algorithm: since we know all flows
   existing in the network, and we know which paths they will take, we
   can know the links available capacity at any point in time.

   Such information is used to determine weather a flow will create
   congestion in a path or not. It would be prefearrable if this data
   would instead be gathered from the snmp-monitoring tool. However,
   it would not be sufficient, since in order to know

3. 

