# Explanation of the TEController algorithms

## General assumptions

1. The flow demands are known to the TEC. The traffic generator
informs the TEC every time there is a new flow starting on the
network. This is essential, since we know which prefix we have to fib.

2. The link utilization is, at the moment, self-maintained by the
algorithm: since we know all flows existing in the network, and we
know which paths they will take, we can know the links available
capacity at any point in time.