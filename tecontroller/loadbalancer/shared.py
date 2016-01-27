import Queue

# Queue used by the json listener thread spawned by the load balancer
# controller
eventQueue = Queue.Queue()
