# Lab 1
This lab shows how fibbing can be used to avoid congestion by moving
the traffic towards an existing destination to an alternative path.

## General assumptions

1. We know the traffic demands on a per-flow basis. The custom written informs our TEController about each new flow that is started on the network. The data includes: src and dst ips and ports, flow size, and duration.

2. We know the routing protocol of the network and, therefore, we can compute the default paths taken by flows. For the case of this semester project, OSPF is used. (However, when at least one router between the ingress and egress routers for that flow have ECMP activated, we are not sure anymore which exact path this flow is going to take.)

3. We only fib existing destination prefixes, and only sinlge-paths are enforced (no ECMP is used in algorithm yet).

4. When trying to allocate flow A matching destination prefix P, we do not move flows to other destinations != P that have already been allocated.
(This means that, upon finding a new path to force to the DAG for a given destination, we must take into account already ongoing flows from all routers in the new path towards the same destination as also part of the "load demand".)

5. The bandwidth of all links in the network is known.

6. The "instantaneous" available capacity for the links of the network is known. To this effect, the [link monitor](https://github.com/lferran/TEController/blob/master/tecontroller/linkmonitor/linksmonitor.py) periodically checks the byte counters for all network interfaces in the network, and updates a data structure mantained in the TEController.

## The algorithm 

### Initialization
- Upon starting, the algorithm reads the current network topology from the fibbing controller as an [IGPGraph](https://github.com/Fibbing/FibbingNode/blob/master/fibbingnode/misc/igp_graph.py).

- For each destination prefix advertized by the routers, it computes the corresponding DAG that specifies the paths taken by the traffic coming from all other possible routers in the network. This step is also aware of ECMP between any two routers. To compute the DAGs, we make use of assumption 2. 

- Such per-prefix destination DAGs will be updated whenever some path is fibbed for a given prefix.

### Explanation

1. The input is a new flow *f* from *f.src* to *f.dst* ips of size *f.size* with a duration of *f.duration*.

2. On the first stage, we compute the longest prefix matching the nF.dst address. This way, we can obtain the corresponding current DAG for that prefix, and calculate the default path that the flow will take. In case ECMP is activated in one of the routers on the way from the ingress router to the egress router, the computed default path will be a list of paths.

3. If ECMP is not enabled, and there is a single path towards the destination prefix, continue to stage 4. Otherwise, jump to stage 10.

4. We check if the flow can be allocated in the default path. To do so, we retrieve the link utilization data from all links of the path thanks to the data structure mantained by the SNMP link monitor. If the link with the lowest available capacity can support the new flow, go to stage 5. Otherwise, continue to stage 6.

5. Note down the flow-to-path allocation for the given destination and finish.

6. Look for the next shortest path that can allocate flow without congestion from src to dst. Does it exist? If so, go to stage 7. Otherwise, continue to stage 9.

7. Check if already existing flows to the same destination that will be moved can be allocated. Since we will enforce a new path in the destination DAG, it is possible that some previously allocated flows will be moved. Therefore, we need to take into account this, and see if the whole traffic demand towards destination running through the new path can be allocated. If so, continue to stage 8. Otherwise, jump back to stage 6.

8. Fib the chosen path. Note down the flow-to-path allocation for the given destination and finish.

9. Choose the path that creates the least global congestion. By least congestion we mean, e.g: that 2 links congested 1% is prefearrable to 1 link congested 5%. Then jump to stage 8.

10. Calculate the probability for this flow to create congestion. Given the flow size, and the two ECMP paths with their respective minimum available capacities, the congestion probability can easily be calculated. With the probabilities, we can then jump to stage 11.

11. Apply a decision function weather to allocate the flow in the default ECMP paths or find an alternative one. This function takes into account the congestion probability, the number of ECMP paths available, etc. If the output of the function is 1, means we should find another path, thus we jump to stage 6. Otherwise, we finish in stage 5.