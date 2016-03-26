from tecontroller.res import defaultconf as dconf
from tecontroller.res.flow import Base
import netifaces as ni
import requests
import argparse
import random
from subprocess import Popen, PIPE

if __name__ == '__main__':
    
    #Searching for own interfaces
    proc = Popen(['netstat', '-i'], stdout=PIPE)
    ip_output = proc.stdout.readlines()
    ifaces = []
    MyETH0Iface = ""
    
    for index, line in enumerate(ip_output):
        ifaces.append(line.split(' ')[0])

    for i in ifaces:
        if 'eth0' in i:
            MyETH0Iface = i

    #Searching for the interface's IP addr
    ni.ifaddresses(MyETH0Iface)
    MyOwnIp = ni.ifaddresses(MyETH0Iface)[2][0]['addr']

    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--action', help="Action: start|stop flow")
    parser.add_argument('-s', '--source', help="Source hostname")
    parser.add_argument('-d', '--destination', help="destination hostname")
    parser.add_argument('--sport', help="source port")
    parser.add_argument('--size', help="size (in bytes)")
    parser.add_argument('--duration', help="flow duration")

    arguments = parser.parse_args()

    if not arguments.action:
        action = 'start'
    elif arguments.action in ['start', 'stop']:
        action = arguments.action
    else:
        action = 'start'
        
    if arguments.source and arguments.destination and arguments.size and arguments.duration and arguments.sport:
        base = Base()
        flow = {'src':arguments.source,
                'dst':arguments.destination,
                'sport':arguments.sport,
                'dport':5001,
                'size':base.setSizeToInt(arguments.size),
                'start_time':0,
                'duration':base.setTimeToInt(arguments.duration)}

        if action == 'start':
            url = "http://%s:%s/startflow"%(MyOwnIp, dconf.TG_JsonPort)
        elif action == 'stop':
            url = "http://%s:%s/stopflow"%(MyOwnIp, dconf.TG_JsonPort)

        requests.post(url, json = flow)
