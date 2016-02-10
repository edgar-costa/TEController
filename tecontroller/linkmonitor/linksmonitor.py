"""This is a python script that will run in a dedicated mininet
host. This host will periodically monitor the load of all links in the
network and will log the corresponding data.

"""

from tecontroller.res.snmplib import SnmpCounters
from tecontroller.res.dbhandler import DatabaseHandler


class LinksMonitor(DatabaseHandler):
    """
    Implements the class.
    """
    def __init__(self):
        super(LinksMonitor, self).__init__()






if __name__ == '__main__':
    
