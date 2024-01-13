#!/usr/bin/env python3

# Getting Watt from diffrent meters
# enter the user data here before calling the script

# What is missing:
# macGH 13.01.2024  Version 0.1.0

import os
import sys
import signal
import atexit
from meter import *


usedmeter           = 7
usedip              = "192.168.179.100"
usedport            = "8087"
useduser            = "username"
usedpass            = "password"
usedvzl_uuid        = "UUID"
usedemlog           = "index" 
usediobrogerobject  = "0_userdata.0.CurrentPower"


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
    
def handle_exit(signum, frame):
    sys.exit(0)

def mwcan_commands():
    print("")
    print(" " + sys.argv[0] + " - Getting meter info")
    print(" Edit data in this py script at the beginning")
    print("")
    print(" Usage:")
    print("        " + sys.argv[0] + " parameter")
    print("")
    print("       readwatt             -- read WATT from meter")
    print("")
    print("       Version 0.1.0 ")


#########################################
# Operation function
def readwatt():
    w = METER.GetPowermeterWatts()
    print("Current WATT: " + str(w))

def command_line_argument():
    if len (sys.argv) == 1:
        print ("")
        print ("Error: First command line argument missing.")
        mwcan_commands()
        error = 1
        return
    
    if sys.argv[1] in ['readwatt'] :  readwatt()
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

METER = meter(usedmeter, usedip, usedport, useduser, usedpass, usedvzl_uuid, usedemlog, usediobrogerobject, LOGLEVEL) 

command_line_argument()

sys.exit(0)
