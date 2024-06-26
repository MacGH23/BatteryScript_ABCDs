#!/usr/bin/env python3

import os
import sys
import subprocess
from time import sleep
from configupdater import ConfigUpdater

def tmux(command):
    os.system('tmux ' + command)

def StartTmuxSession():
    tmux('new-session -d -s BS')

def startBS():
    c = 'send-keys -t BS ' + p + '/BatteryScript.py Enter'
    print(c)
    tmux(c)

def showtmux():
    print("Use CTRL+B -> release -> D to exit Tmux")
    sleep(1)
    tmux('attach -t BS')

def Method_0():
    print("Method 0 - Just restart the Script")
    startBS()

def Method_1():
    print("Method 1")
    try:
#		 Example for changing the paramter before starting the script	
#        updater = ConfigUpdater()
#        updater["Setup"]["BSstart_UsedConfig"].value     = '1'
#        updater["Setup"]["LastDisChargePower_delta"].value    = '10'
#        updater["Setup"]["ZeroDeltaDisChargeWATT"].value      = '10'
#        updater.update_file()
#        #wait 2 seconds 
#        print("Wait 2 seconds ...")
#        sleep(2)
        startBS()
    except Exception as e:
        print(str(e))

def Method_2():
    try:
        updater = ConfigUpdater()
        updater.read("/home/pi/chargerscript/BSsetup.conf")
        updater["Setup"]["BSstart_UsedConfig"].value     = '2'
        updater.update_file()
    except Exception as e:
        print(str(e))

    print("Method 2")
    startBS()

def Method_3():
    try:
        updater = ConfigUpdater()
        updater.read("/home/pi/chargerscript/BSsetup.conf")
        updater["Setup"]["BSstart_UsedConfig"].value     = '3'
        updater.update_file()
    except Exception as e:
        print(str(e))

    print("Method 3")
    startBS()

if len (sys.argv) == 1:
    print("Missing parameter")
    print("Usage:")
    print("Paramater 0..3  : start method 0..3")
    print("Paramater 10..13: same as 0..3 but with 10 seconds delay for startup network")
    print("Paramater 0     : start normal tmux session")
    print("Paramater 1..3  : your own startup")
    print("Paramater 9     : open tmux")
    print("e.g.            : ./BSstart 0")
    sys.exit()

p = os.path.dirname(os.path.abspath(__file__))
print(p)
#Just start using Tmux. Wait 5 seconds to be sure the last session is closed completly 
print("WAIT 5 seconds to start ... ")
sleep(5)

m = int(sys.argv[1])
if(m > 10): #indicate sleep during reboot
    sleep(10)
    m = m - 10

StartTmuxSession()

if(m == 0): Method_0()
if(m == 1): Method_1()
if(m == 2): Method_2()
if(m == 3): Method_3()
if(m == 9): showtmux()
print("EXIT")
sys.exit(1)

