#!/bin/bash

printf "################################################\n"
printf "# Installations Script for ABCDs BatteryScript #\n"
printf "# Need to run with sudo                        #\n"
printf "################################################\n\n"

#System wide apt package
apt install python3-can
apt install python3-psutil
apt install python3-schedule
apt install python3-smbus

#System pip3 package which are not available via apt
#Install paho-mqtt with pip3 because v2.x is needed
pip3 install --break-system-packages paho-mqtt
pip3 install -U --break-system-packages paho-mqtt
pip3 install --break-system-packages pyserial
pip3 install --break-system-packages ifcfg
pip3 install --break-system-packages minimalmodbus
pip3 install --break-system-packages configupdater

apt install --assume-yes tmux
apt install --assume-yes git

usermod -a -G tty $USER
systemctl stop ModemManager
systemctl disable ModemManager

git clone https://github.com/MacGH23/BatteryScript_ABCDs.git BatteryScript_ABCDs

chmod 755 ./BatteryScript_ABCDs/BatteryScript.py
chmod 755 ./BatteryScript_ABCDs/BSstart.py
chmod 755 ./BatteryScript_ABCDs/ShowBS.sh

printf "################################################\n"
printf "# Add manually entry to crontab when ready     #\n"
printf "#  crontab -e                                  #\n"
printf "#  (add at the end:)                           #\n"
printf "#  @reboot /home/pi/BatteryScript_ABCDs/BSstart.py 10        #\n"
printf "################################################\n"

