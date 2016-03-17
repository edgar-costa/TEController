# TEController
This repositoriy holds the code implemented during a
Semester Project in the Electrical Engineering and Information
Technology MSc at ETH Zürich, in the Networked Systems Lab.

The initial purpose of the thesis was to build a network application
on top of Fibbing. The outcome of the work so far has been to write
the TEController, which stands for Traffic Engineering Controller and
is a network application that load balances the traffic of a given
network by means of moving flows to alternative paths. To do so, it
uses the Fibbing controller, to which it gives a Direct Acyclic Graph
(DAG) for a specific destination prefix as an input.

The various strategies that have been explored in order to
load-balance networks are summarized in the three different labs under
the labs/ folder.

The code is organized under the tecontroller/loadbalancer/ folder. The
rest of the python scripts are tools that have been written for the
purpose of testing and/or monitoring the results of the network
application.