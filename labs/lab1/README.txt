# Lab 1
This lab shows how fibbing can be used to avoid congestion by moving
the traffic towards an existing destination to an alternative path.

## General assumptions

1. We know the traffic demands on a per-flow basis. The custom written informs our TEController about each new flow that is started on the network. The data includes: src and dst ips and ports, flow size, and duration.

2. We know the routing protocol of the network and, therefore, we can compute the default paths taken by flows. For the case of this semester project, OSPF is used. (However, when at least one router between the ingress and egress routers for that flow have ECMP activated, we are not sure anymore which exact path this flow is going to take.)

3. We only fib existing destination prefixes.

4. When trying to allocate flow A matching destination prefix P, we do not move flows to other destinations != P that have already been allocated.
(This means that, upon finding a new path to force to the DAG for a given destination, we must take into account already ongoing flows from all routers in the new path towards the same destination as also part of the "load demand".)


## The algorithm 

### Initialization
* Upon starting, the algorithm reads the current network topology from the fibbing controller as an IGPGraph.

* For each destination prefix advertized by the routers, it computes the corresponding DAG that specifies the paths taken by the traffic coming from all other possible routers in the network. This step is also aware of ECMP between any two routers. To compute the DAGs, we make use of assumption 2. 

### Explanation

* The input is a new flow nF from nF.src to nF.dst ips of size nF.s with a duration of nF.d.
* On the first stage


