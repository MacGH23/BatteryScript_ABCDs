#!/usr/bin/env python3

# Reading dalibms with interface UART

# macGH 26.07.2024  Version 0.1.0

import os
import sys
import signal
import atexit
from time import sleep
from daly_bms_lib import *


# "" = default = "/dev/ttyUSB00"
# if you have another device specify here
DEVPATH = "/dev/ttyUSB0" 
#USEDIDADR = 1

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
logpath = "dalybms.log"

##################################################################
##################################################################


def on_exit():
    print("CLEAN UP ...")
    daly.dalybms_close()
    
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


daly = dalybmslib(DEVPATH,0,LOGLEVEL)
daly.dalybms_open()
sleep(0.5)
ST = daly.dalybms_read();


i = 0
print("Cellcount: " + str(daly.cell_count))                                                                                                    
for i in range(daly.cell_count) :                                                                             
    print("CellVolt" + str(i) + ": " + str(daly.cells[i]/1000))                                                                                                    

print("Temp_fet : " + str(daly.temp_fet))                                                                                                    
print("Temp_1   : " + str(daly.temp_1))                                                                                                    
print("temp_2   : " + str(daly.temp_2))                                                                                                    
print("BatVolt  : " + str(daly.voltage/100))                                                                                                    
print("Current  : " + str(daly.act_current/100))                                                                                                    
print("SOC      : " + str(daly.soc))                                                                                                    
print("WATT     : " + str(int((daly.voltage * daly.act_current) / 10000 )))                                                                                                    
         
sys.exit(0)
