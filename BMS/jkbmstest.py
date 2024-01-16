#!/usr/bin/env python3

# Reading jkbms with new interface

# macGH 13.01.2024  Version 0.1.0

import os
import sys
import signal
import atexit
from jkbms import *


# "" = default = "/dev/ttyUSB00"
# if you have another device specify here
DEVPATH = "/dev/ttyAMA0" #with Waveshare CAN/RS485 HAT 
#DEVPATH = "/dev/ttyUSB0" 
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
logpath = "jkbms.log"

##################################################################
##################################################################


def on_exit():
    print("CLEAN UP ...")
    jk.jkbms_close()
    
def handle_exit(signum, frame):
    sys.exit(0)


#### Main 
atexit.register(on_exit)
signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

mylogs = logging.getLogger()
mylogs.setLevel(LOGLEVEL)

if logtofile == 1:
    file = logging.FileHandler(logpath, mode='a')
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


jk = jkbms(DEVPATH,LOGLEVEL)
jk.jkbms_open()
sleep(0.5)
ST = jk.jkbms_read();


i = 0
print("Cellcount: " + str(jk.cell_count))                                                                                                    
for i in range(jk.cell_count) :                                                                             
    print("CellVolt" + str(i) + ": " + str(jk.cells[i]/1000))                                                                                                    

print("Temp_Fet : " + str(jk.temp_fet))                                                                                                    
print("Temp_1   : " + str(jk.temp_1))                                                                                                    
print("temp_2   : " + str(jk.temp_2))                                                                                                    
print("BatVolt  : " + str(jk.voltage/100))                                                                                                    
print("Current  : " + str(jk.act_current/100))                                                                                                    
print("RemCap   : " + str(jk.soc))                                                                                                    
         
sys.exit(0)
