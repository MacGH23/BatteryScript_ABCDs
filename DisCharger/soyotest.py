#!/usr/bin/env python3

# Controlling the Soyo1000W/1200W

# Requirement for using
# Needed external python modules

# What is missing:

# macGH 30.06.2024  Version 0.1.0

import os
import sys
import signal
import atexit
from soyo485 import *


# "" = default = "/dev/ttyAMA0"
DEVPATH = "" 

# Enter Loglevel 0,10,20,30,40,50 
# CRITICAL   50
# ERROR      40
# WARNING    30
# INFO       20
# DEBUG      10
# NOTSET      0
LOGLEVEL     = 20
logtofile    =  0
logtoconsole =  1

def on_exit():
    print("CLEAN UP ...")
    soyo.soyo485_close()
    
def handle_exit(signum, frame):
    sys.exit(0)

def mwcan_commands():
    print("")
    print(" " + sys.argv[0] + " - controlling the Soyo1000/1200")
    print("")
    print(" Usage:")
    print("        " + sys.argv[0] + " parameter and <value>")
    print("")
    print("       setwatt              -- set WATT outout")
    print("")
    print("       Version 0.1.0 ")


#########################################
# Operation function


def setwatt(val):
    # print ("Set output in WATT")
    # Set output in Watt
    v = soyo.set_watt_out(val) 
    return v


def command_line_argument():
    if len (sys.argv) == 1:
        print ("")
        print ("Error: First command line argument missing.")
        mwcan_commands()
        error = 1
        return
    
    if sys.argv[1] in ['setwatt']  : setwatt(int(sys.argv[2]))
    else:
        print("")
        print("Unknown first argument '" + sys.argv[1] + "'")
        mwcan_commands()
        error = 1
        return

#### Main 
atexit.register(on_exit)
signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

mylogs = logging.getLogger()
mylogs.setLevel(LOGLEVEL)

if logtofile == 1:
    file = logging.FileHandler(self.logpath, mode='a')
    file.setLevel(LOGLEVEL)
    fileformat = logging.Formatter("%(asctime)s:%(module)s:%(levelname)s:%(message)s",datefmt="%H:%M:%S")
    file.setFormatter(fileformat)
    mylogs.addHandler(file)

if logtoconsole == 1:
    stream = logging.StreamHandler()
    stream.setLevel(LOGLEVEL)
    streamformat = logging.Formatter("%(asctime)s:%(module)s:%(levelname)s:%(message)s",datefmt="%H:%M:%S")
    stream.setFormatter(streamformat)    
    mylogs.addHandler(stream)


soyo = soyo485(DEVPATH, LOGLEVEL)
soyo.soyo485_open()

command_line_argument()

sys.exit(0)
