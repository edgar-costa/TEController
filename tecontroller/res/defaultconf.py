"""
Default configuration file
"""
#Package path
PPATH = '/root/TEController/'

# Hostname of the Traffic Engineering Controller host in the network.
LBC_Hostname = 'c3'

# Hostname of the Traffic Generator host in the network.
TG_Hostname = 'c2'

#Port on which the JSON-aware thread of the LBC is listening
LBC_JsonPort = "5500"

# Port on which TG listens for json-flask commands
TG_JsonPort = '5000'

# Place where the topology information is being stored inside the vm
# (and the hosts)
DB_Path = '/tmp/db.topo'

# File where the parameters to connect to the Southbound controller
# are found
C1_Cfg = '/tmp/c1.cfg'

# Path of the Traffic Generator package
TG_Path = PPATH + 'tecontroller/trafficgenerator/'

# Path to the Traffic Engineering controller package
LBC_Path = PPATH + 'tecontroller/loadbalancer/'

# Path to Link Monitorer package
LM_Path = PPATH + 'tecontroller/linkmonitor/'

# Path to Resources folder
RES_Path = PPATH + 'tecontroller/res/'

# Path to Labs
Labs_Path = PPATH + 'labs/'
Lab0_Path = Labs_Path + 'lab0/'
Lab1_Path = Labs_Path + 'lab1/'
Lab2_Path = Labs_Path + 'lab2/'
Lab3_Path = Labs_Path + 'lab3/'

# Paths to test folders
Lab0_Tests = Lab0_Path + 'tests/'
Lab1_Tests = Lab1_Path + 'tests/'
Lab2_Tests = Lab2_Path + 'tests/'

# Default port for the json-daemons for the hosts in the network
Hosts_JsonPort = "5000"

# Path to the file where the flows definition for the Traffic
# Generator are stored
defaultFlowFile = TG_Path + 'flowfile.csv'

# Waiting time (in seconds) for hosts to check their IP
Hosts_InitialWaitingTime = 10
LBC_InitialWaitingTime = 20
TG_InitialWaitingTime = 30
FeedbackThreadWaitingTime = Hosts_InitialWaitingTime

# Default port for which IPERF server is listening in the custom hosts
Hosts_DefaultIperfPort = '5001'

# Log folder for the hosts
Hosts_LogFolder = PPATH + "logs/"

# Log file for linksmonitor
LinksMonitor_LogFile = PPATH + "logs/links.log"

## SNMP commands
# Start agent
START_SNMP_AGENT = '/usr/sbin/snmpd'
SNMP_CommunityString = 'linkmonitor'

# Marshal filename for the probability calculator object
MarshalFile = RES_Path +'dictionarydump.marshal'

# Path where the .cap files of the routers are saved
CAP_Path = PPATH + "logs/"

