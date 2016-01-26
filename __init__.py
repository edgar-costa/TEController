import ConfigParser
import os

#Path to config directory
RES = os.path.join(os.path.dirname(__file__), 'res')


CFG = ConfigParser.ConfigParser()
with open(os.path.join(RES, 'default.cfg', 'r') as f:
          CFG.readfp(f)
