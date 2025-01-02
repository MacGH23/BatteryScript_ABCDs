#!/usr/bin/env python3

# Controlling the Lumentree 600/1000/2000

# Requirement for using
# Needed external python modules

# What is missing:

# macGH 26.11.2023  Version 0.2.3

import os
import sys
import signal
import atexit
from lt232 import *


# "" = default = "/dev/ttyUSB0"
# if you have another device specify here
#0=Lumentree
#1=Trucki RS485
DEVTYPE = 0
DEVPATH = "" 
USEDIDADR = 1

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
    lt.lt232_close()
    
def handle_exit(signum, frame):
    sys.exit(0)

def mwcan_commands():
    print("")
    print(" " + sys.argv[0] + " - controlling the Lumentree 600/1000/2000 devices")
    print("")
    print(" Usage:")
    print("        " + sys.argv[0] + " parameter and <value>")
    print("")
    print("       setwatt              -- set WATT outout")
    print("       readwatt             -- read WATT outout")
    print("       vread                -- read DC voltage")
    print("       acvread              -- read AC voltage")
    print("       tempread             -- read power supply temperature")
    print("")
    print("       Version 0.1.0 ")


#########################################
# Operation function


def vread():
    # print ("read dc voltage")
    # Read DC Voltage
    v = lt.readDCvoltage()
    print(v)
    return v

def acvread():
    # print ("read ac voltage")
    # Read AC Voltage
    v = lt.readACvoltage()
    print(v)
    return v

def tempread():
    # print ("read power supply temperature")
    # Read AC Voltage
    v = lt.readtemp()
    print(v)
    return v

def setwatt(val):
    # print ("Set output in WATT")
    # Set output in Watt
    v = lt.set_watt_out(val) 
    return v

def readwatt():
    # print ("Set output in WATT")
    # Set output in Watt
    v = lt.read_watt_out() 
    print(v)
    return v

def command_line_argument():
    if len (sys.argv) == 1:
        print ("")
        print ("Error: First command line argument missing.")
        mwcan_commands()
        error = 1
        return
    
    if sys.argv[1]   in ['vread']    : vread()
    elif sys.argv[1] in ['acvread']  : acvread()
    elif sys.argv[1] in ['tempread'] : tempread()
    elif sys.argv[1] in ['setwatt']  : setwatt(int(sys.argv[2]))
    elif sys.argv[1] in ['readwatt'] : readwatt()
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


lt = lt232(DEVTYPE, DEVPATH,USEDIDADR,LOGLEVEL)
lt.lt232_open()

command_line_argument()

sys.exit(0)
