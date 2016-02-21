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
    parser.add_argument('-s', '--source', help="Source hostname")
    parser.add_argument('-d', '--destination', help="destination hostname")
    parser.add_argument('--size', help="size (in bytes)")
    parser.add_argument('--duration', help="flow duration")

    args = parser.parse_args()
    if args.source and args.destination and args.size and args.duration:

        base = Base()
        flow = {'src':args.source,
                'dst':args.destination,
                'sport':random.randint(1025, 65000),
                'dport':5001,
                'size':base.setSizeToInt(args.size),
                'start_time':0,
                'duration':base.setTimeToInt(args.duration)}

        url = "http://%s:%s/startflow"%(MyOwnIp, dconf.LBC_JsonPort)
        requests.post(url, json = flow)
