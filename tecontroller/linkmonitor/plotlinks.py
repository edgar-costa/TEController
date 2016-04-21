"""Script that creates the plots for the observer loads of the links
in the network.
"""
from tecontroller.res import defaultconf as dconf
import numpy as np
import matplotlib.pyplot as plt
import time
import argparse
from scipy import signal

def main(args):
    
    start = time.time()

    # Parse arguments
    if args.all:
        edges_to_print = "ALL"
    else:
        tmp = args.only_links.split(',')
        edges_to_print = [i.strip('[').strip(']') for i in tmp]
        
    print "Edges to print: %s"%str(edges_to_print)

    if args.timeframe_max:
        until = int(args.timeframe_max)
    else:
        until = None

    if args.timeframe_min:
        fromm = int(args.timeframe_min) + 8
    else:
        fromm = 8
        
    # Open links logfile
    f = open(dconf.LinksMonitor_LogFile, 'r') # LINKS LOGFILE
    lines = f.readlines()
    lines = [line.strip('\n').split(',') for line in lines]
    edges_t = lines[0]
    lines = lines[1:]

    links = [a.split('->')[0] for a in edges_t if a]
    edges = [a.split('->')[1] for a in edges_t if a]

    if args.all ==True:
        edges_to_print = edges
        

    offset = 8
    seconds = np.asarray([float(line[0]) for line in lines])
    seconds = seconds - seconds[0] - offset# make time relative to start


    
    data = [line[1:] for line in lines]

    
    loads = []
    for line in data[fromm:until]:
        values = []
        for i, v in enumerate(line):
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
    count = 1
    for i, l in enumerate(links):

        [tmpx, tmpy] = edges[i].strip('(').strip(')').split(' ')
        edge_tmp = "(%s %s)"%(tmpy,tmpx)

        if edges[i] in edges_to_print or edge_tmp in edges_to_print:
            ax = fig.add_subplot(len(edges_to_print), 1, count)
            label = l+" %s"%edges[i].replace(' ', ', ')
            label_f = label+' filtered'
            ax.plot(seconds[fromm:until], loads[:,i], 'r.', label=label)
            ax.plot(seconds[fromm:until], loads2[:,i], 'b-', label=label_f)
            ax.set_ylim(0,150)
            ax.legend([label, label_f], loc='right')
            #ax.legend([label_f], loc='right')
            ax.grid(True)
            count += 1
    plt.suptitle('Load of links over time')
    plt.show()
    plt.savefig(dconf.Hosts_LogFolder+'links.png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-l', '--only-links',
                       type=str,
                       default="[(s1 r1),(s2 r1),(r1 r2),(r1 r3),(r1 r4),(r4 r3),(r3 d1)]")
    group.add_argument('--all', action='store_true', default=False)
    parser.add_argument('--timeframe_max')
    parser.add_argument('--timeframe_min')
    args = parser.parse_args()
    main(args)
