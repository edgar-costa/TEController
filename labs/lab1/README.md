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

6. The "instantaneous" available capacity for the links of the network is known. To this effect, the [link monitor](https://github.com/lferran/TEController/blob/master/tecontroller/linkmonitor/linksmonitor.py) and [link monitor thread](https://github.com/lferran/TEController/blob/master/tecontroller/linkmonitor/linksmonitor_thread.py) periodically checks the byte counters for all network interfaces in the network, and updates a data structure mantained in the TEController.

## The algorithm 

### Diagram

![alt tag](https://github.com/lferran/TEController/blob/master/labs/lab1/lab1-algorithm.png)

### Initialization
- Upon starting, the algorithm reads the current network topology from the fibbing controller as an [IGPGraph](https://github.com/Fibbing/FibbingNode/blob/master/fibbingnode/misc/igp_graph.py).

- For each destination prefix advertized by the routers, it computes the corresponding DAG that specifies the paths taken by the traffic coming from all other possible routers in the network. This step is also aware of ECMP between any two routers. To compute the DAGs, we make use of assumption 2. 

- Such per-prefix destination DAGs will be updated whenever some path is fibbed for a given prefix.

### Explanation

1. The input is a new flow *f* from *f.src* to *f.dst* ips of size *f.size* with a duration of *f.duration*.

2. On the first stage, we compute the longest prefix matching the nF.dst address. This way, we can obtain the corresponding current DAG for that prefix, and calculate the default path that the flow will take. In case ECMP is activated in one of the routers on the way from the ingress router to the egress router, the computed default path will be a list of paths.

3. If ECMP is not enabled, and there is a single path towards the destination prefix, continue to stage 4. Otherwise, jump to stage 10.

4. We check if the flow can be allocated in the default path. To do so, we retrieve the link utilization data from all links of the path thanks to the data structure mantained by the SNMP link monitor. If the link with the lowest available capacity can support the new flow, go to stage 5. Otherwise, the flowAllocationAlgorithm is called, continuing in stage 6.

5. Note down the flow-to-path allocation for the given destination and finish.

6. Initially, the flowAllocationAlgorithm computes all possible different paths from source to destination. It filters out those that already can't allocate the new flow without congestoin because they contain at least a link with available capacity smaller that the flow size. If it finds at least. If it can find at least one path that can allocate the new flow, jump to stage 7. Otherwise, continue to stage 9.

7. Check if already existing flows to the same destination that will be moved can be allocated. Since we will enforce a new path in the destination DAG, it is possible that some previously allocated flows for the same destination will be moved when applying the new DAG. Therefore, we need to take into account this, and see if the whole traffic demand towards destination running through the new path can be allocated. If so, continue to stage 8. Otherwise, jump back to stage 6 by checking the next existent shortest-path.

8. Fib the chosen path. Note down the flow-to-path allocation for the given destination and finish.

9. Choose the path that creates the least global congestion. By least congestion we mean, e.g: that 2 links congested 1% is prefearrable to 1 link congested 5%. What is done in practice is: We order all existing different paths by decreasing minimum available capacity. For each of them, we compute how much congestion is eventually created when allocating the new flow and moving the already ongoing flows. Finally, we choose the one that creates the minimum congestion. Finally, we jump to stage 8.

10. Calculate the probability for this flow to create congestion. Given the flow size, and the two ECMP paths with their respective minimum available capacities, the congestion probability can easily be calculated. With the probabilities, we can then jump to stage 11.

11. Apply a decision function weather to allocate the flow in the default ECMP paths or find an alternative one. This function takes into account the congestion probability, the number of ECMP paths available, etc. If the output of the function is 1, means we should find another path, thus we jump to stage 6. Otherwise, we finish in stage 5.


### Limitations

1. At the moment, the data structure that holds the instantaneous link available capacities is just a thread that periodically sends SNMP queries to all routers in the network to ask for their interface counters. The interface counters, though, are only updated every second, and this is a clear limitation of our algorithm. For instance, if two flows start in the second elapsed between two successive counter updates, the second flow will not take into account the capacity consumption created by the first one. (Actually, it's even worse, since we are using a 3-sample window median filter on the capacity read-outs -> new flows spaced less than 3 seconds will not be allocated correctly...  
This could be overcomed by using the flow-allocations instead to determine the available capacity of a link. SNMP/sFlow measurements could be used only as a feedback loop when there is ECMP and we are not sure where the flows are actually being allocated in reality. However, this has the drawback that there is some traffic going through the links that is not orchestrated by the traffic generator (such as the SNMP queries/responses, for instance) and this could represent a not negligible part of the total bandwidth for small links (~100K of uncontrolled traffic).

2. Since the monitoring tool is SNMP, and the SNMP requests/replies are also sent in the network, when there is congestion in the network, the SNMP data arrives with high delay and thus our TEController reacts even slower. This might be happening due to: a) The routers in the network are very busy sending data to the interfaces and the SNMP requests are handled with less priority. b) The delay is caused by the congestion in the network links. 
A solution to this problem would be to