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
    seconds = np.asarray([float(line[0]) for line in lines])
    seconds = seconds - seconds[0] # make time relative to start
    
    data = [line[1:] for line in lines]
    links = []
    for element in data[0]:
        links.append(element.split(' ')[0].strip('('))

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
    fig = plt.figure()
    for i, l in enumerate(links):
        ax = fig.add_subplot('%d1%d'%(len(links), i+1))
        ax.plot(seconds, loads[:,i], 'r-', label=l)
        ax.plot(seconds, loads2[:,i], 'b-', label=l+' filtered')
        ax.set_ylim(0,100)
        ax.legend([l, l+' filtered'], loc='right')
        ax.grid(True)
        
    plt.suptitle('Load of links over time')
    plt.show()
    plt.savefig(dconf.Hosts_LogFolder+'links.png')


if __name__ == '__main__':
    main()
