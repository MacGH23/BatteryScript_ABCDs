#!/usr/bin/env python3

# Getting Watt from diffrent meters
# enter the user data here before calling the script

# What is missing:
# macGH 13.01.2024  Version 0.1.0
# macGH 18.02.2024  Version 0.1.1

import os
import sys
import signal
import atexit
from meter import *

# Meter
# 1: SHELLY_EM
# 2: SHELLY_3EM
# 3: SHELLY_3EMPRO
# 4: TASMOTA
# 5: SHRDZM
# 6: EMLOG
# 7: IOBROKER
# 8: HOMEASSISTANT
# 9: VZLOGGER
#10: SHELLY1PM
#11: SHELLYPLUS1PM
#12: SHELLYPRO1PM

usedmeter           = 4
usedip              = "192.168.179.10"
usedport            = "80"
useduser            = "username"
usedpass            = "password"
usedvzl_uuid        = "UUID"
usedemlog           = "index" 
usediobrogerobject  = "YourCurrentPowerName"


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

def meter_commands():
    print("")
    print(" " + sys.argv[0] + " - Getting meter info")
    print(" Edit data in this py script at the beginning")
    print("")
    print(" Usage:")
    print("        " + sys.argv[0] + " parameter")
    print("")
    print("       readwatt             -- read WATT from meter")
    print("")
    print("       Version 0.1.1 ")


#########################################
# Operation function
def readwatt():
    try:
        w = METER.GetPowermeterWatts()
        print("Current WATT: " + str(w))
    except Exception as e:
        logging.error("ERROR DURING READING")
        logging.error(str(e))

def command_line_argument():
    if len (sys.argv) == 1:
        print ("")
        print ("Error: First command line argument missing.")
        meter_commands()
        error = 1
        return
    
    if sys.argv[1] in ['readwatt'] :  readwatt()
    else:
        print("")
        print("Unknown first argument '" + sys.argv[1] + "'")
        meter_commands()
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
