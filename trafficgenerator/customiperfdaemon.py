#!/usr/bin/python

from subprocess import Popen, PIPE
import flask
import traceback
from subprocess import call
import netifaces as ni
from time import sleep

app = flask.Flask(__name__)

@app.route("/startflow", methods = ['POST'])
def trafficGeneratorSlave():
    """This function will be running in each of the hosts in our
    network. It essentially waits for commands from the
    TrafficGenerator in the Json-Rest interface and creates a
    subprocess for each corresponding iperf client sessions to other
    hosts.

    """
    flow = flask.request.json
    try:
        Popen(["iperf", "-c", flow['dst'], "-u",
               "-b", str(flow['size']),
               "-t", str(flow['duration']),
               "-p", str(flow['dport'])])
    except Exception, err:
        print flow
        print(traceback.format_exc())


if __name__ == "__main__":

    #Waiting for the IP's to be assigned...
    sleep(10)
    
    #Searching for host's own interfaces
    proc = Popen(['netstat', '-i'], stdout=PIPE)
    ip_output = proc.stdout.readlines()
    ifaces = []
    MyETH0Iface = "CACA"
    
    for index, line in enumerate(ip_output):
        ifaces.append(line.split(' ')[0])

    for i in ifaces:
        if 'eth0' in i:
            MyETH0Iface = i

    print MyETH0Iface
    #Searching for the interface's IP addr
    ni.ifaddresses(MyETH0Iface)
    MyOwnIp = ni.ifaddresses(MyETH0Iface)[2][0]['addr']
    print MyOwnIp
    
    app.run(host=MyOwnIp)
