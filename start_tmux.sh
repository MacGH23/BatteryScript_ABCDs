#!/bin/bash
#need to wait for the network 10 Seconds after a reboot
printf "WAIT 10 Secondes for Network\n"

sleep 10
tmux new-session -d -s BS '/home/pi/chargerscript/BatteryScript.py'
