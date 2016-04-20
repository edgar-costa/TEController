"""Script that creates the plots for the observer loads of the links
in the network.
"""
from tecontroller.res import defaultconf as dconf
import numpy as np
import matplotlib.pyplot as plt
import time
import argparse
from scipy import signal
import matplotlib

#matplotlib.rcParams['legend.handlelength'] = 0
#matplotlib.rcParams['legend.numpoints'] = 1

def extractData(logfile):
    # Here we store all data from logfile
    data_dict = {}
    
    # Read al lines of logfile first
    lines = logfile.readlines()
    
    # Remove \n and split by ','
    lines = [line.strip('\n').split(',') for line in lines]

    # Get logged edges line 
    edges_t = lines[0]

    # Remove edge line from top
    lines = lines[1:]

    # Fill data dict with edges 
    for edge_t in edges_t:
        if edge_t != '':
            link = edge_t.split('->')[0]
            edge = edge_t.split('->')[1]
            x = edge.split(' ')[0].strip('(')
            y = edge.split(' ')[1].strip(')')
            edge = (x,y)
            data_dict[link] = {'edge': edge}

    ## Get time axis (in seconds)
    seconds = np.asarray([float(line[0]) for line in lines])
    # Make time relative to start
    seconds = seconds - seconds[0]
    
    # Add it into data_dict
    data_dict['time_axis'] = seconds

    # Separate other data
    data = [line[1:] for line in lines]

    # Iterate data and load it in data dictionary
    # First fill tmp dict with loads
    tmp_loads = {}
    for l in data_dict.keys():
        if l != 'time_axis':
            tmp_loads[l] = []

    for line in data:
        # Iterate value edges in line
        for v in line:
            # Get link 
            link = v.split(' ')[0].strip('(')
            value = float(v.split(' ')[1].strip('%)'))
            # Add value in list of values per link
            tmp_loads[link].append(value)

    # Add it into data_dict
    for link, values in tmp_loads.iteritems():
        if link != 'time_axis':
            # Convert to np array
            values = np.asarray(values)
            data_dict[link]['values'] = values

    # Compute filtered output with a median filter
    for link in data_dict.keys():
        if link != 'time_axis':
            values = data_dict[link]['values']
            filtered = signal.medfilt(values)
            data_dict[link]['filtered'] = filtered

    logfile.close()
    return data_dict


def main(args):
    ## Arguments should be parsed here
    # Check which test is it
    test = args.test
    if not test:
        return 

    # Get links to output
    if not args.links:
        all_links = True
    else:
        all_links = False
        links = args.links
        links_to_plot = []
        for l in links.split(','):
            x = l.split(' ')[0].strip('(')
            y = l.split(' ')[1].strip(')')
            links_to_plot.append((x,y))

    if args.timeframe_max:
        max_s = args.timeframe_max
    else:
        max_s = None

    if args.timeframe_min:
        min_s = args.timeframe_min
    else:
        min_s = None        

    #Open logfile no loadbalancing
    no_lb = open('./'+test+'/'+test+'_no_lb.log', 'r')

    #Open logfile weight optimization
    wo = open('./'+test+'/'+test+'_wo.log', 'r')

    #Open logfile loadbalancer
    lb = open('./'+test+'/'+test+'_lb.log', 'r')

    # Extract data from each logfile
    no_lb_data = extractData(no_lb)
    wo_data = extractData(wo)
    lb_data = extractData(lb)

    # PLOTS ###################################
    fig = plt.figure(1)
    count = 1

    # Lines for legend
    lines = []

    for link in links_to_plot:
        # Add new subplot for edge
        ax = fig.add_subplot(len(links_to_plot), 1, count)
        
        # Colors are the same all the time:
        colors = ['r-', 'b-', 'g-']
        
        # Gather data from all three logfiles
        for i, logfile_data in enumerate([no_lb_data, wo_data, lb_data]):
            # Get time axis
            time = logfile_data['time_axis']
            
            # Get link name
            link_name = [l for l in logfile_data.keys() if
                    'L' in l and logfile_data[l].get('edge') and
                    logfile_data[l].get('edge') == link]

            if not link_name:
                import ipdb; ipdb.set_trace()
                
            else:
                link_name = link_name[0]

            # Get filtered output
            values_f = logfile_data[link_name]['filtered']
            
            # Plot it
            line, = ax.plot(time, values_f, colors[i], linewidth=2)
            lines.append(line)

        # Set y axis limit for subplot
        ax.set_ylim(-0.5,105)
       
        # Set label for that link
        label = "(%s, %s)"%(link[0], link[1])

        ax.legend([label], loc='right', handlelength=0, numpoints=1)

        ax.grid(True)
        count += 1


    fig.subplots_adjust(bottom=0.10, left=0.10, right=0.90, top=0.90, wspace=0.2, hspace=0.24)
    fig.legend((lines[0], lines[1], lines[2]), ("Without Load-Balancing","Optimizing Weights","Fibbing TEC"), ncol=3, borderaxespad=3, loc=9,)

    fig.text(0.06, 0.5, 'Link utilization (%)', ha='center', va='center', rotation='vertical', fontsize=18)
    plt.xlabel("Time (s)", fontsize=18)
    #import ipdb; ipdb.set_trace()
    plt.show()
    #plt.savefig(dconf.Hosts_LogFolder+'links.png')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-l', '--links', type=str)
    group.add_argument('--all', action='store_true', default=True)
    parser.add_argument("-t", "--test")
    parser.add_argument('--timeframe_max', type=int)
    parser.add_argument('--timeframe_min', type=int)
    args = parser.parse_args()
    main(args)
