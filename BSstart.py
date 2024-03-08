#!/usr/bin/env python3

import os
import sys
from time import sleep

def tmux(command):
    os.system('tmux %s' % command)

def starttmux():
    tmux('new-session -d -s BS ' + p + '/BatteryScript.py')

def showtmux():
    print("Use CTRL+B -> release -> D to exit Tmux")
    sleep(1)
    tmux('attach -t BS')

def Method_0():
    #Just restart using Tmux
    print("Method 0")
    starttmux()

def Method_1():
    #print("Method 1")

def Method_2():
    print("Method 2")

def Method_3():
    print("Method 3")

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

p = os.path.dirname(__file__)

m = int(sys.argv[1])
if(m > 10): #indicate sleep during reboot
    sleep(10)
    m = m - 10

if(m == 0): Method_0()
if(m == 1): Method_1()
if(m == 2): Method_2()
if(m == 3): Method_3()
if(m == 9): showtmux()
print("EXIT")
sys.exit(1)

