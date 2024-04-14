#!/usr/bin/env python3

# Controlling external switch for constant based charger
#
# macGH 12.04.2024  Version 0.1.0

import os
import sys
import logging
from constbased import *

####################################################
#Constant Based Charger with external switch
#Devid: 
#0: Tasmota
#Use MaxChargeWATT to specify the output power
CBC_devid = 0
CBC_ipadr = "192.168.2.71"
CBC_user  = ""
CBC_pass  = ""

# Enter Loglevel 0,10,20,30,40,50 
# CRITICAL   50
# ERROR      40
# WARNING    30
# INFO       20
# DEBUG      10
# NOTSET      0
LOGLEVEL     = 20
logtofile    = 0
logtoconsole = 1

def mwcan_commands():
    print("")
    print(" " + sys.argv[0] + " - controlling external switch for constant based charger")
    print("")
    print(" Usage:")
    print("        " + sys.argv[0] + " parameter and <value>")
    print("")
    print("       on                      -- output on")
    print("       off                     -- output off")

#########################################
# Operation function

def operation(val):#0=off, 1=on
    if(val == 0):
        r = cbc.PowerOff();
    if(val == 1):
        r = cbc.PowerOn();
    
    if(r!=-1):
        if(r==0):
            print("Return OFF: " + str(r))
        if(r==1):
            print("Return ON : " + str(r))
    else:
        print("Return ERROR: " + str(r))
    
    return


def command_line_argument():
    if len (sys.argv) == 1:
        print ("")
        print ("Error: First command line argument missing.")
        mwcan_commands()
        error = 1
        return
    
    if   sys.argv[1] in ['on']:        operation(1)
    elif sys.argv[1] in ['off']:       operation(0)
    else:
        print("")
        print("Unknown first argument '" + sys.argv[1] + "'")
        error = 1
        return

#### Main 
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

cbc = ChargerConstBased(CBC_devid,CBC_ipadr,CBC_user,CBC_pass,LOGLEVEL)
command_line_argument()

sys.exit(0)
