#!/usr/bin/env python3

import os
import psutil
import sys
import schedule
import time
from time import sleep

def is_running(script):
    for q in psutil.process_iter():
        if q.name().startswith('python3'):
            if len(q.cmdline())>1 and script in q.cmdline()[1] and q.pid !=os.getpid(): #cmdline
                print("'{}' Process is already running".format(script))
                return True

    return False


def CheckScript():
    if not is_running("ChargeScript.py"):
       print ("Is not Running")
       
schedule.every(2).seconds.do(CheckScript)                      # Start every 2s

while True:
    schedule.run_pending()
    sleep(1)

