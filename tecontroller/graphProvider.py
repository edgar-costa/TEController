from fibbingnode.algorithms.southbound_interface import SouthboundManager
from fibbingnode import CFG
from fibbingnode.misc.mininetlib.ipnet import TopologyDB
import threading


HAS_GRAPH = threading.Event()

DB_path = '/tmp/db.topo'
C1_cfg = '/tmp/c1.cfg'

class MyGraphProvider(SouthboundManager):
    def received_initial_graph(self):
        HAS_GRAPH.set()


def do_stuff_with_graph(graph):
    for src, dst, data in graph.edges_iter(data=True):
        print (src, dst, data)
        pass


def run(mngr):
    try:
        mngr.run()
    except KeyboardInterrupt:
        mngr.stop()
        
    
def main():
    CFG.read(C1_cfg)
    db = TopologyDB(db=DB_path)

    mngr = MyGraphProvider()
    t = threading.Thread(target=run, args=(mngr,), name="Graph Listener")
    t.start()
    HAS_GRAPH.wait() #Blocks until set
    import ipdb; ipdb.set_trace()#TRACEEEEEEEEEEEEEEEEEE
    do_stuff_with_graph(mngr.igp_graph)
    mngr.stop()
    print "Ciaoo"
    
if __name__ == '__main__':
    main()
    print "Ciao"
    
