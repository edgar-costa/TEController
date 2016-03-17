# TEController
Traffic Engineering Controller: network application using Fibbing.

This repositoriy holds the code implemented during a Semester Project in the Electrical Engineering and Information Technology MSc at ETH Zürich, in the Networked Systems Lab.

The initial purpose of the thesis was to build a network application on top of Fibbing. The outcome of the work so far has been to write the TEController, which is a program that load balances the traffic of the network by means of moving flows to alternative paths. To do so, it uses the Fibbing controller, to which it gives a Direct Acyclic Graph (DAG) for a specific destination prefix as an input.
