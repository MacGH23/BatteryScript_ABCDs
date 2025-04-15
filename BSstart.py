#!/usr/bin/env python3

import os
import sys
import subprocess
import requests
from time import sleep
from configupdater import ConfigUpdater

debug = 0

def tmux(command):
    if(debug == 1):
        print('CMD: ' + command + "\n")
    os.system('tmux ' + command)

def StartTmuxSession():
    tmux('new-session -d -s BS')

def startBS():
    #clear Buffer in case some Char left
    c = 'send-keys -t BS clear Enter'
    tmux(c)
    sleep(0.5)
    c = 'send-keys -t BS ' + p + '/BatteryScript.py Enter'
    tmux(c)

def showtmux():
    print("Use CTRL+B -> release -> D to exit Tmux")
    sleep(1)
    tmux('attach -t BS')

def Method_0():
    startBS()

def Method_1():
    try:
        updater["Setup"]["BSstart_UsedConfig"].value     = '1'
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
        updater["Setup"]["BSstart_UsedConfig"].value         = '2'
        startBS()
    except Exception as e:
        print(str(e))

def Method_3():
    try:
        updater["Setup"]["BSstart_UsedConfig"].value         = '3'
        updater.update_file()
        startBS()
    except Exception as e:
        print(str(e))

def Method_4():
    try:
        updater["Setup"]["BSstart_UsedConfig"].value         = '4'
        updater.update_file()
        startBS()
    except Exception as e:
        print(str(e))

def Method_5():
    try:
        updater["Setup"]["BSstart_UsedConfig"].value         = '5'
        updater.update_file()
        startBS()
    except Exception as e:
        print(str(e))

def Method_6():
    try:
        updater["Setup"]["BSstart_UsedConfig"].value         = '6'
        updater.update_file()
        startBS()
    except Exception as e:
        print(str(e))

def Method_7():
    try:
        updater["Setup"]["BSstart_UsedConfig"].value         = '7'
        updater.update_file()
        startBS()
    except Exception as e:
        print(str(e))

def Method_8():
    try:
        updater["Setup"]["BSstart_UsedConfig"].value         = '8'
        updater.update_file()
        startBS()
    except Exception as e:
        print(str(e))

def check_ping():
    response = os.system("ping -c 1 " + serverip + ">nul")
    # and then check the response...
    #if response == 0:
    #    print("Ping OK")
    #else:
    #    print("NoPing")
    return response

if len (sys.argv) == 1:
    print("Missing parameter")
    print("Usage:")
    print("Paramater 0..8  : start method 0..8")
    print("Paramater 10..18: same as 0..8 but with 10 seconds delay for startup network")
    print("Paramater 0     : start normal tmux session")
    print("Paramater 1..8  : your own startup")
    print("Paramater 9     : open tmux")
    print("e.g.            : ./BSstart 0")
    sys.exit()


p = os.path.dirname(os.path.abspath(__file__))
#Just start using Tmux. Wait 3 Seconds to be sure the last session is closed
if(debug == 1):
    print("WAIT 3 seconds to start ...")
sleep(3)

m = int(sys.argv[1])
if(m > 10): #indicate sleep during reboot
    sleep(10)
    m = m - 10

#Check if server for PowerMeter is running, otherwise don't start
updater = ConfigUpdater()
updater.read(p + "/BSsetup.conf")
BSstart_UseServerPing =  int(updater["Setup"]["BSstart_UseServerPing"].value)

if(BSstart_UseServerPing == 1):
    maxwait = 30 #wait max x seconds*2 (ping needs 1 second + sleep(1)) and start script to init the rest if necessary 
    GetPowerOption =  int(updater["Setup"]["GetPowerOption"].value)
    if(GetPowerOption == 0): #mqtt
        serverip = updater["Setup"]["mqttserver"].value
    if(GetPowerOption == 1): #http
        serverip = updater["Setup"]["http_ip_address"].value

    serveralive = check_ping()
    try:
        while((serveralive !=0) and (maxwait > 0)):
            serveralive = check_ping()
            maxwait = maxwait - 1
            print("Server " + str(serverip) + " not ready. Wait: " + str(maxwait))
            sleep(1)
    except KeyboardInterrupt:
        print('Script stop!')
        sys.exit(0)

StartTmuxSession()

if(m == 0): Method_0()
if(m == 1): Method_1()
if(m == 2): Method_2()
if(m == 3): Method_3()
if(m == 4): Method_4()
if(m == 5): Method_5()
if(m == 6): Method_6()
if(m == 7): Method_7()
if(m == 8): Method_8()
if(m == 9): showtmux()

if(debug == 1):
    print("Method " + str(m) + " used")
    print("Path Used:")
    print(__file__)
    print(p)
    print("EXIT")
sys.exit(1)

