"""Script that creates the plots for the observer loads of the links
in the network.
"""
from tecontroller.res import defaultconf as dconf
import numpy as np
import matplotlib.pyplot as plt
import time
from scipy import signal

def main():
    start = time.time()
    
    # Open links logfile
    f = open(dconf.LinksMonitor_LogFile, 'r') # LINKS LOGFILE
    lines = f.readlines()
    lines = [line.strip('\n').split(',') for line in lines]
    edges_t = lines[0]
    lines = lines[1:]

    links = [a.split('->')[0] for a in edges_t if a]
    edges = [a.split('->')[1] for a in edges_t if a]
    
    seconds = np.asarray([float(line[0]) for line in lines])
    seconds = seconds - seconds[0] # make time relative to start
    
    data = [line[1:] for line in lines]

    loads = []
    for line in data:
        values = []
        for i,v in enumerate(line):
            values.append(float(v.split(' ')[1].strip('%)')))
        loads.append(values)
    loads = np.asarray(loads)

    print "It took %d seconds to read data"%(time.time()-start)

    # Filtered output with a median filter
    loads2 = np.zeros((len(loads[:,0]), 1))
    for i in range(loads.shape[1]):
        col = loads[:,i]
        col = signal.medfilt(col)
        loads2 = np.insert(loads2, i+1, col, axis=1)

    loads2 = loads2[:,1:]

    # PLOTS ###################################
    fig = plt.figure(1)
    fig.subplots_adjust(bottom=0.04, left=0.04, right=0.98, top=0.96, wspace=0.2, hspace=0.24)

    for i, l in enumerate(links):
        ax = fig.add_subplot(len(links),1,i+1)
        label = l+" %s"%edges[i].replace(' ', ', ')
        label_f = label+' filtered'
        ax.plot(seconds, loads[:,i], 'r.', label=label)
        ax.plot(seconds, loads2[:,i], 'b-', label=label_f)
        ax.set_ylim(0,100)
        ax.legend([label, label_f], loc='right')
        ax.grid(True)

    plt.suptitle('Load of links over time')
    plt.show()
    plt.savefig(dconf.Hosts_LogFolder+'links.png')


if __name__ == '__main__':
    main()
