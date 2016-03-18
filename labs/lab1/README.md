# Lab 1
This lab shows how fibbing can be used to avoid congestion by moving
the traffic towards an existing destination to an alternative path.

## General assumptions

1. We know the traffic demands on a per-flow basis. The custom written informs our TEController about each new flow that is started on the network. The data includes: src and dst ips and ports, flow size, and duration.

2. We know the routing protocol of the network and, therefore, we can compute the default paths taken by flows. For the case of this semester project, OSPF is used. (However, when at least one router between the ingress and egress routers for that flow have ECMP activated, we are not sure anymore which exact path this flow is going to take.)

3. We only fib existing destination prefixes.

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

3. If ECMP is not enabled, and there is a single path towards the destination prefix, continue to stage 4.

4. We check if the flow can be allocated in the default path. To do so, we retrieve the link utilization data from the SNMP link monitor of all links along the default path. It the link with the lowest available capacity can support the new flow, go to stage 5. Otherwise, continue to stage 6.

5. Note down the flow-to-path allocation for the given destination and finish.

6. Look for the next shortest congestion-free path from src to dst.

To this

20. Otherwise, if ECMP is enabled, we jump to stage  can compute the probability of this flow to create congestion in the network.



