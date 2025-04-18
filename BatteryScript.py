#!/usr/bin/env python3

# Script for automatic charging and discharge your Battery
# Not suitable for productive use.
# Use for demo purposes only !
# Use on own risk !

##########################################################################################
# Installation
# Install tmux
# sudo apt install tmux
#
# Needed external python3 modules use pip or pip3 depands on your environment
# pip3 install pyserial
# pip3 install paho-mqtt
# if you already have installed paho-mqtt < 2.0
# pip3 install -U paho-mqtt
# pip3 python-can
# pip3 opencan
# pip3 install ifcfg
# pip3 install minimalmodbus
# pip3 install configupdater
# pip3 install psutil
# pip3 install schedule
##########################################################################################
# Hints
# For the serial communication the user must be added to dialout group
# sudo usermod -a -G tty $USER
# Disable ModemManager to prevent scanning COM ports
# sudo systemctl stop ModemManager
# sudo systemctl disable ModemManager
#
# API mqtt:   https://eclipse.dev/paho/index.php?page=clients/python/docs/index.php
# API modbus: https://minimalmodbus.readthedocs.io/en/stable/apiminimalmodbus.html#apiminimalmodbus
##########################################################################################

# Version history
# macGH 13.01.2024  Version 0.1.0: initial version
# macGH 31.01.2024  Version 0.1.5: added Webserver, Wh Calculation, cleanup
# macGH 04.02.2024  Version 0.1.6: added BatteryWh estimation
# macGH 09.02.2024  Version 0.1.7: added voltage check for discharger
# macGH 11.02.2024  Version 0.1.8: fixed save & restore of EstBatteryWh
# macGH 14.02.2024  Version 0.1.9: fixed BIC-2200 DisCharger function
# macGH 15.02.2024  Version 0.2.0: added mw Voltage correction
# macGH 25.02.2024  Version 0.2.1: Improved BIC-2200 handling for always on
# macGH 03.02.2024  Version 0.2.2: Fixed some bugs. Start adding Temperature checks
# macGH 08.02.2024  Version 0.2.3: Fixed BIC2200 Alwayson prevent stop during shutdown;added Restartbuttons;Added Temperature check
# macGH 11.02.2024  Version 0.2.4: Fixed tmux restart problem
# macGH 26.03.2024  Version 0.2.5: Fixed Temperature reading
# macGH 26.03.2024  Version 0.2.6: Update EEPROM Write Check for MW
# macGH 10.04.2024  Version 0.2.7: Added Constant Based Charger via external switch
# macGH 24.04.2024  Version 0.2.8: Update to paho-mqtt 2.0, fixed MW Check EEPROM Write
# macGH 10.05.2024  Version 0.2.9: Some small changes
# macGH 17.05.2024  Version 0.3.0: Some changes and changes with mwcanlib
# macGH 04.06.2024  Version 0.3.1: Errorhandling during powermeter dis/rereconnect
# macGH 14.06.2024  Version 0.3.2: Added NPB Voltage adaption for smaller than Mincurrent charge, added ZerodeltaChargerWatt
# macGH 16.07.2024  Version 0.3.3: Added Soyo 1000W/1200W - experimental; improved meterdelay, some small changes
# macGH 26.07.2024  Version 0.3.4: Added DalyBMS - Should work but not 100%tested
# macGH 27.07.2024  Version 0.3.5: Update BMS handling
# macGH 09.08.2024  Version 0.3.5: Update Web Server
# macGH 24.08.2024  Version 0.4.0: Added SASBBMS based on https://github.com/mr-manuel/venus-os_dbus-serialbattery -> much more BMS supported now
#                                  Added power swap if meter send the value in wrong format
#                                  Addad customizable mqtt actions for web interface
# macGH 27.08.2024  Version 0.4.1: Added BMSConnectionLost status
# macGH 09.10.2024  Version 0.4.2: Added LCDReinit for webinterface
# macGH 29.10.2024  Version 0.4.3: Added BIC2200 almost empty
# macGH 07.11.2024  Version 0.4.4: Update BIC2200 almost empty
# macGH 09.11.2024  Version 0.4.5: Added ProcessActive to prevent 2nd start before all was proceed
# macGH 09.11.2024  Version 0.4.6: Fixed BIC2200 always on Battery almost full issue (fast switch charge <> discharge)
# macGH 22.11.2024  Version 0.4.7: Added mPSU CAN
# macGH 09.12.2024  Version 0.4.8: Fixed BIC2200 Battery empty start
# macGH 30.12.2024  Version 0.4.9: Added mPSU RS485 interface
# macGH 10.01.2025  Version 0.5.0: Added mqtt publish EstWh
# macGH 18.04.2025  Version 0.5.1: Added Change MaxChargeCurrent in WebInterface

import os
import sys
import time
from time import sleep
import json
import requests
import datetime
import signal
import atexit
import schedule
import logging, logging.handlers
import random
import psutil
from configupdater import ConfigUpdater
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO
import subprocess

# Device classes
from Charger.mwcan import *
from DisCharger.lt232 import *
from DisCharger.soyo485 import *
from Meter.meter import *
from Charger.constbased import *

# import external funtions
from BatteryScript_external import *

# LCD import
from LCD.hd44780_i2c import i2clcd

# Add BMS path, needed for DALYBMS
padd = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(1, padd + "/BMS")  # the type of path is string
from jkbms import *
from daly_bms_lib import *

sys.path.insert(1, padd + "/SASB")  # the type of path is string
from standalone_serialbattery import *

if os.path.isfile(padd + "/Charger/mPSU_can.py"):
    from Charger.mPSU_can import *
    from Charger.mPSU_rs485 import *


#######################################################################
# WEBSERVER CLASS #####################################################
#######################################################################


class WS(BaseHTTPRequestHandler):

    def _set_headers(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        return

    def _gettableentry(self, parameter, value, page):
        Button = "n.a."
        if(page != 'config'): 
            if (
                (parameter == "ChargerEnabled")
                or (parameter == "DisChargerEnabled")
                or (parameter == "WebAutoRefresh")
                or (parameter == "MW_NBPVoltageAdjust")
                or (parameter == "ShowRuntime")
            ):
                Button = f'<form action="/" method="post"><button name={parameter} type="submit" value={parameter}>Toggle ON/OFF</button></form>'

            if "MaxChargeCurrent" in parameter:
                Button = f'<form action="/" method="post"> \
                        <button name={parameter} type="submit" value={parameter}_25>25%</button> \
                        <button name={parameter} type="submit" value={parameter}_50>50%</button> \
                        <button name={parameter} type="submit" value={parameter}_75>75%</button> \
                        <button name={parameter} type="submit" value={parameter}_100>100%</button><br> \
                        <button name={parameter} type="submit" value={parameter}_10>10%</button> \
                        <button name={parameter} type="submit" value={parameter}_20>20%</button> \
                        <button name={parameter} type="submit" value={parameter}_30>30%</button> \
                        <button name={parameter} type="submit" value={parameter}_40>40%</button> \
                        <button name={parameter} type="submit" value={parameter}_60>60%</button> \
                        <button name={parameter} type="submit" value={parameter}_70>70%</button> \
                        <button name={parameter} type="submit" value={parameter}_80>80%</button> \
                        <button name={parameter} type="submit" value={parameter}_90>90%</button></form>'

            if "MQTT_" in parameter:
                Button = f'<form action="/" method="post"><button name={parameter} type="submit" value={parameter}>Execute MQTT Action</button></form>'

            if "EXT_" in parameter:
                Button = f'<form action="/" method="post"><button name={parameter} type="submit" value={parameter}>Execute EXTERNAL Action</button></form>'

            if parameter == "EstBatteryWh":
                Button = f'<form action="/" method="post"><button name={parameter} type="submit" value={parameter}>Reset to 0</button></form>'

            if parameter == "ReInitLCD":
                Button = f'<form action="/" method="post"><button name={parameter} type="submit" value={parameter}>Reinit i2c LCD</button></form>'

            if (parameter == "Reboot") or (parameter == "Shutdown") or ("RestartMethod" in parameter):
                Button = f'<form action="/" method="post"><button name={parameter} type="submit" value={parameter}>Press 3 times</button></form>'

                # f'<input type="text" name="EstBatteryWhValue" placeholder="{value}">' + \
                #'<label for="Minwatt">Minwatt:</label>\n'+ \
                #'<input type="text" id="Minwatt" name="Minwatt"><br><br>\n'+ \
                #'<button type="submit">Submit</button>\n'+ \
                #'<button type="submit" formmethod="post">Submit using POST</button>\n' + \

        tabcontent = (
            "<tr>\n"
            + f'<td style="border-style: solid; border-width: 1px;"><p>{parameter}</p></td>\n'
            + f'<td style="border-style: solid; width: 50px; text-align: center; border-width: 1px;">{value}</td>\n'
            + f'<td style="border-style: solid; border-width: 1px;">{Button}</td>\n'
            + "</tr>\n"
        )

        return tabcontent

    def _beginhtml(self, message, refreshtime, pagepath):
        if status.WebAutoRefresh == 0:
            refreshtime = -1

        content = (
            "<!DOCTYPE HTML>\n"
            + "<html>\n"
            + "<head>\n"
            + f'<meta http-equiv="refresh" content="{refreshtime}">\n'
            + "<title>ABCDs Script Web Server</title>\n"
            + f'<base href={cfg.WSipadr}:{cfg.WSport}/"  target="_parent"/>\n'
            + "</head>\n"
            + "<body>\n"
            + "<h1>Welcome to ABCDs WebServer Interface</h1>\n"
            + '<p style="font-size:1.4vw;"><a href="/">Global Status</a>&nbsp;&nbsp;&nbsp;'
            + '<a href="/config">Config</a>&nbsp;&nbsp;&nbsp;'
            + '<a href="/bms">BMS status</a>&nbsp;&nbsp;&nbsp;'
            + '<a href="/system">System Status</a>&nbsp;&nbsp;&nbsp;'
            + '<a href="/mqtt">Actions</a>&nbsp;&nbsp;&nbsp;</p>'
            + "<br><br>\n<b>"
            + message
            + "</b></h1><br>\n"
        )

        """
                      f'<form action="{pagepath}" method="post"><button name=Refresh type="submit" value=Refresh>Refresh site</button></form>'+\
                      message + \
                      '</b></h1><br>\n'
            """

        return content

    def _endhtml(self):
        content = "</body>\n" + "</html>\n"
        return content

    def _confightml(self, message):
        content = ""
        for attr, value in vars(cfg).items():
            content = content + self._gettableentry(attr, value,'config')

        content = (
            self._beginhtml(message, -1, "/config")
            + '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;font-size:1.1vw;">'
            + "<tbody>"
            + content
            + "</tbody>"
            + "</table>"
            + self._endhtml()
        )

        return content.encode("utf8")  # NOTE: must return a bytes object!

    def _bmshtml(self, message):
        content = ""
        for attr, value in vars(BMSstatus).items():
            # if((attr == "BMSCurrent") or (attr == "BMSVoltage")): attr = str(int(attr)/100)
            content = content + self._gettableentry(attr, value,'bms')

        content = (
            self._beginhtml(message, 30, "/bms")
            + '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;font-size:1.1vw;">'
            + "<tbody>"
            + content
            + "</tbody>"
            + "</table>"
            + self._endhtml()
        )

        return content.encode("utf8")  # NOTE: must return a bytes object!

    def _systemhtml(self, message):
        content = (
            self._gettableentry("CPU usage in %", psutil.cpu_percent(),'system')
            + self._gettableentry("RAM usage in %", psutil.virtual_memory().percent,'system')
            + self._gettableentry(
                "CPU Temperature &deg;C",
                int(psutil.sensors_temperatures()["cpu_thermal"][0].current),'system'
            )
            + self._gettableentry("Reboot", status.WebRebootSDcounter,'system')
            + self._gettableentry("Shutdown", status.WebRebootSDcounter,'system')
            + self._gettableentry("RestartMethod0", status.WebRebootSDcounter,'system')
            + self._gettableentry("RestartMethod1", status.WebRebootSDcounter,'system')
            + self._gettableentry("RestartMethod2", status.WebRebootSDcounter,'system')
            + self._gettableentry("RestartMethod3", status.WebRebootSDcounter,'system')
        )

        content = (
            self._beginhtml(message, -1, "/system")
            + '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;font-size:1.1vw;">'
            + "<tbody>"
            + content
            + "</tbody>"
            + "</table>"
            + self._endhtml()
        )

        return content.encode("utf8")  # NOTE: must return a bytes object!

    def _actionhtml(self, message):
        content = (
            self._gettableentry("MQTT_" + cfg.mqttaction1name + "_1", 0,'action')
            + self._gettableentry("MQTT_" + cfg.mqttaction2name + "_2", 0,'action')
            + self._gettableentry("MQTT_" + cfg.mqttaction3name + "_3", 0,'action')
            + self._gettableentry("MQTT_" + cfg.mqttaction4name + "_4", 0,'action')
            + self._gettableentry("EXT_1", 0,'action')
            + self._gettableentry("EXT_2", 0,'action')
            + self._gettableentry("EXT_3", 0,'action')
            + self._gettableentry("EXT_4", 0,'action')
        )

        content = (
            self._beginhtml(message, -1, "/system")
            + '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;font-size:1.1vw;">'
            + "<tbody>"
            + content
            + "</tbody>"
            + "</table>"
            + self._endhtml()
        )

        return content.encode("utf8")  # NOTE: must return a bytes object!

    def _statushtml(self, message):
        content = (
            self._beginhtml(str(message), 30, "/")
            + '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;font-size:1.1vw;">\n'
            + "<tbody>\n"
            + self._gettableentry("CurrentWattValue", status.CurrentWattValue,'status')
            + self._gettableentry("CurrentTotalWatt", status.CurrentTotalWatt,'status')
            + self._gettableentry("CurrentAverageWatt", status.CurrentAverageWatt,'status')
            + self._gettableentry("LastWattValueUsedinDevice", status.LastWattValueUsedinDevice,'status')
            + self._gettableentry("BatteryVoltage", status.BatteryVoltage / 100,'status')
            + self._gettableentry("BMSSOC", status.BMSSOC,'status')
            + self._gettableentry("EstBatteryWh", round(status.EstBatteryWh / 1000),'status')
            + self._gettableentry("MaxChargeCurrent", status.MaxChargeCurrent,'status')
            + self._gettableentry("BatteryFull", status.BatteryFULL,'status')
            + self._gettableentry("BatteryEmpty", status.BatteryEMPTY,'status')
            + self._gettableentry("ChargerEnabled", status.ChargerEnabled,'status')
            + self._gettableentry("ChargerStatus", status.ChargerStatus,'status')
            + self._gettableentry("DisChargerEnabled", status.DisChargerEnabled,'status')
            + self._gettableentry("DisChargerStatus", status.DisChargerStatus,'status')
            + self._gettableentry("MW_NPB_COUNTER", cfg.MW_NPB_COUNTER,'status')
            + self._gettableentry("MW_BIC_COUNTER", cfg.MW_BIC_COUNTER,'status')
            + self._gettableentry("LT_COUNTER", status.ltcounter,'status')
            + self._gettableentry("WebAutoRefresh", status.WebAutoRefresh,'status')
            + self._gettableentry("ReInitLCD", "",'status')
            + "</tbody>\n"
            + "</table>\n"
            + "</form>\n"
            + self._endhtml()
        )

        #'<form action="/" method="get">\n'+ \
        #'<label for="Maxwatt">Maxwatt:</label>'+ \
        #'<input type="text" id="Maxwatt" name="Maxwatt"><br><br>\n'+ \
        #'<label for="Minwatt">Minwatt:</label>\n'+ \
        #'<input type="text" id="Minwatt" name="Minwatt"><br><br>\n'+ \
        #'<button type="submit">Submit</button>\n'+ \
        #'<button type="submit" formmethod="post">Submit using POST</button>\n' + \
        return content.encode("utf8")  # NOTE: must return a bytes object!

    def do_GET(self):
        mylogs.debug("WebServer: GET")
        self._set_headers()
        if self.path == "/":
            self.wfile.write(self._statushtml("Read Status"))
        if self.path == "/config":
            self.wfile.write(self._confightml("Read Global Config"))
        if self.path == "/bms":
            self.wfile.write(self._bmshtml("Read BMS status"))
        if self.path == "/system":
            self.wfile.write(self._systemhtml("Read System status"))
        if self.path == "/mqtt":
            self.wfile.write(self._actionhtml("Action"))
        if "/MAXCHARGECURRENT_" in self.path:
            ispercent = self.path[-1:]
            if(ispercent == '%'):
                newvalue = int(self.path[18:-1])
                if(newvalue >= 0) and (newvalue <= 100):
                    status.MaxChargeCurrent = round((cfg.MaxChargeCurrent / 100) * newvalue)
                    status.MaxChargeCurrentChange = 1
                    mylogs.info("DIRECTWebServerRequest: MaxChargeCurrent new value: "+ str(status.MaxChargeCurrent))
                    self.wfile.write(self._statushtml(self.path))
                else:
                    mylogs.info("DIRECTWebServerRequest: ONLY 0..100% is allowed")
                    self.wfile.write(self._statushtml(self.path))
            else:
                status.MaxChargeCurrent = int(self.path[18:])
                if(status.MaxChargeCurrent > cfg.MaxChargeCurrent):
                    status.MaxChargeCurrent = cfg.MaxChargeCurrent
                if(status.MaxChargeCurrent < cfg.MinChargeCurrent):
                    status.MaxChargeCurrent = cfg.MinChargeCurrent
                status.MaxChargeCurrentChange = 1
                mylogs.info("DIRECTWebServerRequest: MaxChargeCurrent new value: "+ str(status.MaxChargeCurrent))
                self.wfile.write(self._statushtml(self.path))

        if "/DIRECTRESTART" in self.path:
            n = self.path[-1]
            p = os.path.dirname(__file__)
            self.wfile.write(self._statushtml("DIRECTRESTART ! NR " + str(n)))
            subprocess.Popen([p + "/BSstart.py", n], start_new_session=True)
            # subprocess.Popen([sys.executable, 'BSstart.py',n], start_new_session=True)
            sys.exit(1)

        return

    def do_HEAD(self):
        self._set_headers()
        return

    def do_POST(self):
        mylogs.debug("WebServer: POST")
        self._set_headers()
        todo = ""

        content_length = int(self.headers["Content-Length"])
        bodybytes = self.rfile.read(content_length)
        bodystr = bodybytes.decode("UTF-8")
        bodyitem = bodystr.split("&")

        bodyitems = {}
        for item in bodyitem:
            variable, value = item.split("=")
            bodyitems[variable] = value
            mylogs.info("WebServer: " + variable + " - " + value)

            if variable == "MaxChargeCurrent":
                todo = "MaxChargeCurrent changed"
                newvalue = int(value[17:])
                status.MaxChargeCurrent = round((cfg.MaxChargeCurrent / 100) * newvalue)
                status.MaxChargeCurrentChange = 1
                mylogs.info("WebServer: MaxChargeCurrent button pressed - New value: "+ str(status.MaxChargeCurrent))
                self.wfile.write(self._statushtml(todo))

            if variable == "ChargerEnabled":
                mylogs.info("WebServer: ChargerEnabled button pressed")
                todo = "ChargerEnabled Toggle done"
                status.ChargerEnabled = 1 - status.ChargerEnabled
                self.wfile.write(self._statushtml(todo))

            if variable == "DisChargerEnabled":
                mylogs.info("WebServer: DisChargerEnabled button pressed")
                todo = "DisChargerEnabled Toggle done"
                status.DisChargerEnabled = 1 - status.DisChargerEnabled
                self.wfile.write(self._statushtml(todo))

            if variable == "WebAutoRefresh":
                mylogs.info("WebAutoRefresh button pressed")
                todo = "WebAutoRefresh Toggle done"
                status.WebAutoRefresh = 1 - status.WebAutoRefresh
                self.wfile.write(self._statushtml(todo))

            if variable == "MW_NBPVoltageAdjust":
                mylogs.info("MW_NBPVoltageAdjust button pressed")
                todo = "MW_NBPVoltageAdjust Toggle done"
                cfg.MW_NBPVoltageAdjust = 1 - cfg.MW_NBPVoltageAdjust
                self.wfile.write(self._confightml(todo))

            if variable == "ShowRuntime":
                mylogs.info("ShowRuntime button pressed")
                todo = "ShowRuntime Toggle done"
                cfg.ShowRuntime = 1 - cfg.ShowRuntime
                self.wfile.write(self._confightml(todo))

            if variable == "EstBatteryWh":
                mylogs.info("EstBatteryWh reset button pressed")
                todo = "EstBatteryWh reset to 0 done"
                status.EstBatteryWh = 0
                self.wfile.write(self._statushtml(todo))

            if variable == "Reboot":
                status.WebRebootSDcounter += 1
                todo = "Press 3 times to reboot: " + str(status.WebRebootSDcounter)
                if status.WebRebootSDcounter == 3:
                    todo = "Reboot now ..."
                    self.wfile.write(self._systemhtml(todo))
                    on_exit()
                    os.system("sudo reboot")
                self.wfile.write(self._systemhtml(todo))

            if variable == "Shutdown":
                status.WebRebootSDcounter += 1
                todo = "Press 3 times to shutdown: " + str(status.WebRebootSDcounter)
                if status.WebRebootSDcounter == 3:
                    todo = "Shutdown !"
                    self.wfile.write(self._systemhtml(todo))
                    on_exit()
                    os.system("sudo shutdown -P now")
                self.wfile.write(self._systemhtml(todo))

            if variable == "ReInitLCD":
                LCDinit()
                self.wfile.write(self._statushtml(todo))

            if "Restart" in variable:
                n = variable[-1]
                p = os.path.dirname(__file__)
                status.WebRebootSDcounter += 1
                todo = "Press 3 times to use Restart Method " + n + ": " + str(status.WebRebootSDcounter)
                if status.WebRebootSDcounter == 3:
                    todo = "Execute Restart Method " + n + " !"
                    self.wfile.write(self._systemhtml(todo))
                    # subprocess.Popen([sys.executable, p +'/BSstart.py',n], start_new_session=True)
                    subprocess.Popen([p + "/BSstart.py", n], start_new_session=True)
                    sys.exit(1)
                self.wfile.write(self._systemhtml(todo))

            if "MQTT_" in variable:
                n = variable[-1]
                todo = "Action NR: >" + n + "< executed"
                mqttactionpublish(n)
                self.wfile.write(self._actionhtml(todo))

            if "EXT_" in variable:
                n = variable[-1]
                todo = "EXT Action NR: >" + n + "< executed"
                externalaction(n)
                self.wfile.write(self._actionhtml(todo))

        return

    # Get the log handler to prevent to print all to the screen
    def log_request(self, code=None, size=None):
        host, port = self.client_address[:2]
        mylogs.info("<-> HTTP Request from: " + host + " - Site: " + self.path)


#        def log_message(self, format, *args):
#            print('Message')


#######################################################################
# WEBSERVER CLASS END #################################################
#######################################################################


#########################################
##class devices, contains all devices used
class DEV:
    def __init__(self):
        self.display = None
        self.mwcandev = None
        self.mPSU = None
        self.LT1 = None
        self.LT2 = None
        self.LT3 = None
        self.soyo = None
        self.jk = None
        self.daly = None
        self.sasb = None
        self.mqttclient = None


#########################################
##class config
class BMS:
    def __init__(self):
        self.BMSSOC = 0  # Battery State of Charge status if BMS is used, if not 100% is used
        self.BMSCurrent = 0
        self.BMSVoltage = 0  # Voltage of BMS
        self.BMSTemp_Mosfet = 0
        self.BMSTemp1 = 0
        self.BMSTemp2 = 0
        self.BMSTemp3 = 0
        self.BMSTemp4 = 0
        self.CellCount = 0
        self.BMSCellVoltage = []
        for x in range(24):
            self.BMSCellVoltage.append(x)
            self.BMSCellVoltage[x] = 0


class Devicestatus:

    def __init__(self):
        self.configfile = ""
        self.LastEstWhTime = datetime.datetime.now()  # init with start time
        self.LastStartRunTime = datetime.datetime.now()  # init with start time for last message
        self.LastEndRunTime = datetime.datetime.now()  # init with start time for last message
        self.CheckDeviceTime = datetime.datetime.now()  # init with start time for last message
        self.ProcessActive = 0
        self.MaxRunTime = 0.1
        self.ChargerEnabled = 1  # for remote enable and disable
        self.DisChargerEnabled = 1  # for remote enable and disable
        self.CurrentWattValue = 0  # from Meter
        self.CurrentTotalWatt = 0  # Used for Device charger or discharger; -x = SOLAR, +x = GRID
        self.CurrentAverageWatt = 0  # Current calculated Average Watt
        self.LastWattValueUsedinDevice = 0  # Used in the Device charger or discharger; -x = SOLAR, +x = GRID depends on max min vlaues
        self.LastChargerSetCurrent = 0
        self.LastChargerGetCurrent = 0
        self.LastDisChargerGetCurrent = 0
        self.LastDisChargerSetCurrent = 0
        self.MaxChargeCurrent = 0           #use for max chargecurrent to modify during operation
        self.MaxChargeCurrentChange = 0     #Trigger to check new value
        self.BICChargeDisChargeMode = 0  # 0=Charge, 1 = DisCharge
        self.LastChargerMode = 0
        self.ChargerStatus = 0
        self.DisChargerStatus = 0
        self.ChargerMainVoltage = 0  # must be set during init of the charger to 12V, 24V, 48V or 92V
        self.ZeroExportWatt = 0
        self.ZeroImportWatt = 0
        self.BatteryFULL = 0  # 0=no, 1=Full
        self.BatteryEMPTY = 0  # 0=no, 1=EMPTY
        self.BatteryVoltage = 0  # Battery Voltage to check charging status, this is used for calculation
        self.BMSSOC = 100  # Battery State of Charge status if BMS is used, if not 100% is used
        self.BMSCurrent = 0
        self.BMSVoltage = 0  # Voltage of BMS
        self.BMSConnectionLost = 0  # Status of BMS read operation
        self.EstBatteryWh = 0
        self.ChargerVoltage = 0  # Voltage of Charger
        self.DisChargerVoltage = 0  # Voltage of DisCharger
        self.LastPowerArrayPosition = -1  # increase in first step --> 1st entry is 0
        self.actchargercounter = 100  # only change values after x METER values --> all 2 Seconds new value with chargercounter = 5 => 10seconds, first start ok -> 100
        self.waitchargercounter = 0
        self.DisCharger_efficacy_factor = float(0)
        self.WebAutoRefresh = 0
        self.WebRebootSDcounter = 0
        self.LT1_Temperature = 0
        self.LT2_Temperature = 0
        self.LT3_Temperature = 0
        self.MW_NPB_Temperature = 0
        self.MW_EEPromOff = 0
        self.MW_BIC_Temperature = 0
        self.MW_ChargeVoltage = 0
        self.mPSU_ChargeVoltage = 0
        self.mPSU_Temperature = 0
        self.ltcounter = 0
        self.ext_lastwattusedindevice = 0  # if User add another external dis-/charger, this can be set for calculation
        self.ext_info = 0


class chargerconfig:

    def iniread(self):
        try:
            updater = ConfigUpdater()
            updater.read(status.configfile)

            self.loglevel = int(updater["Setup"]["loglevel"].value)
            self.logpath = str(updater["Setup"]["logpath"].value)
            self.logtoconsole = int(updater["Setup"]["logtoconsole"].value)
            self.logtofile = int(updater["Setup"]["logtofile"].value)
            self.logappendfile = int(updater["Setup"]["logappendfile"].value)
            self.logtosyslog = int(updater["Setup"]["logtosyslog"].value)

            mylogs.setLevel(self.loglevel)

            if self.logtofile == 1:
                if self.logappendfile == 1:
                    filehandler = logging.FileHandler(self.logpath, mode="a")
                else:
                    filehandler = logging.FileHandler(self.logpath, mode="w")
                    # filehandler = logging.handlers.RotatingFileHandler(self.logpath, mode='w', backupCount=2)
                    # filehandler = logging.handlers.TimedRotatingFileHandler(self.logpath, when='midnight', backupCount=7, utc=False)
                    # filehandler = logging.handlers.TimedRotatingFileHandler(self.logpath, when='midnight', backupCount=7, encoding=None, delay=False, utc=False, atTime=None, errors=None)

                filehandler.setLevel(self.loglevel)
                fileformat = logging.Formatter(
                    "%(asctime)s:%(module)s:%(levelname)s:%(message)s",
                    datefmt="%H:%M:%S",
                )
                filehandler.setFormatter(fileformat)
                mem = logging.handlers.MemoryHandler(10 * 1024, 30, filehandler, flushOnClose=True)
                mylogs.addHandler(mem)

            if self.logtoconsole == 1:
                stream = logging.StreamHandler()
                stream.setLevel(self.loglevel)
                streamformat = logging.Formatter(
                    "%(asctime)s:%(module)s:%(levelname)s:%(message)s",
                    datefmt="%H:%M:%S",
                )
                stream.setFormatter(streamformat)
                mylogs.addHandler(stream)

            if self.logtosyslog == 1:
                slhandler = SysLogHandler(facility=SysLogHandler.LOG_DAEMON, address="/dev/log")
                slformat = logging.Formatter(
                    "%(asctime)s:%(module)s:%(levelname)s:%(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
                handler.setFormatter(slformat)
                logger.addHandler(slhandler)

            mylogs.debug("Read config ...")

            self.i_changed_my_config = int(updater["Setup"]["i_changed_my_config"].value)
            self.BSstart_UsedConfig = int(updater["Setup"]["BSstart_UsedConfig"].value)
            self.BSstart_UseServerPing = int(updater["Setup"]["BSstart_UseServerPing"].value)

            self.ShowRuntime = int(updater["Setup"]["ShowRuntime"].value)
            self.MeterDelaytime = int(updater["Setup"]["MeterDelaytime"].value)
            self.MeterSwapValue = int(updater["Setup"]["MeterSwapValue"].value)

            self.ChargerPowerCalcCount = int(updater["Setup"]["ChargerPowerCalcCount"].value)
            self.DisChargerPowerCalcCount = int(updater["Setup"]["DisChargerPowerCalcCount"].value)
            status.powercalccount = self.ChargerPowerCalcCount

            self.CellCount = int(updater["Setup"]["CellCount"].value)
            self.CellAH = int(updater["Setup"]["CellAH"].value)
            self.CellvoltageMax = int(updater["Setup"]["CellvoltageMax"].value)
            self.CellvoltageMin = int(updater["Setup"]["CellvoltageMin"].value)
            self.CellvoltageMaxRestart = int(updater["Setup"]["CellvoltageMaxRestart"].value)
            self.CellvoltageMinRestart = int(updater["Setup"]["CellvoltageMinRestart"].value)

            self.FixedChargeVoltage = self.CellCount * self.CellvoltageMax
            self.StopDischargeVoltage = self.CellCount * self.CellvoltageMin
            self.RestartChargevoltage = self.CellCount * self.CellvoltageMaxRestart
            self.RestartDisChargevoltage = self.CellCount * self.CellvoltageMinRestart
            self.BatteryTotalWH = round(self.CellCount * self.CellAH * 3.2 * 1000)

            self.MaxChargeCurrent = int(updater["Setup"]["MaxChargeCurrent"].value)
            status.MaxChargeCurrent = self.MaxChargeCurrent
            self.MinChargeCurrent = int(updater["Setup"]["MinChargeCurrent"].value)
            self.MaxDisChargeCurrent = int(updater["Setup"]["MaxDisChargeCurrent"].value)
            self.MinDisChargeCurrent = int(updater["Setup"]["MinDisChargeCurrent"].value)
            self.ChargerCurrentDiffHyst = int(updater["Setup"]["ChargerCurrentDiffHyst"].value)
            self.DisChargerCurrentMin = int(updater["Setup"]["DisChargerCurrentMin"].value)
            self.MaxChargeWATT = int(updater["Setup"]["MaxChargeWATT"].value)
            self.MinChargeWATT = int(updater["Setup"]["MinChargeWATT"].value)
            self.LastChargePower_delta = int(updater["Setup"]["LastChargePower_delta"].value)

            self.StopMinChargeCurrent = int(updater["Setup"]["StopMinChargeCurrent"].value)
            self.MaxDisChargeWATT = int(updater["Setup"]["MaxDisChargeWATT"].value)
            self.MinDisChargeWATT = int(updater["Setup"]["MinDisChargeWATT"].value)
            self.ZeroDeltaChargerWATT = int(updater["Setup"]["ZeroDeltaChargerWATT"].value)
            self.ZeroDeltaDisChargeWATT = int(updater["Setup"]["ZeroDeltaDisChargeWATT"].value)
            self.MeterUpdateChargeCounter = int(updater["Setup"]["MeterUpdateChargeCounter"].value)
            self.MeterUpdateDisChargeCounter = int(updater["Setup"]["MeterUpdateDisChargeCounter"].value)
            self.MW_NPB_COUNTER = int(updater["Setup"]["MW_NPB_COUNTER"].value)
            self.MW_BIC_COUNTER = int(updater["Setup"]["MW_BIC_COUNTER"].value)
            self.BatteryVoltageSource = int(updater["Setup"]["BatteryVoltageSource"].value)
            self.BatteryVoltageCorrection = int(updater["Setup"]["BatteryVoltageCorrection"].value)
            self.EstBatteryWh = int(updater["Setup"]["EstBatteryWh"].value)

            self.LastDisChargePower_delta = int(updater["Setup"]["LastDisChargePower_delta"].value)
            self.Voltage_ACIN_correction = int(updater["Setup"]["Voltage_ACIN_correction"].value)

            self.Selected_Device_Charger = int(updater["Setup"]["Selected_Device_Charger"].value)
            self.Selected_Device_DisCharger = int(updater["Setup"]["Selected_Device_DisCharger"].value)
            self.MW_USEDID = updater["Setup"]["MW_USEDID"].value
            self.MW_BIC2200_ForceAlwaysOn = int(updater["Setup"]["MW_BIC2200_ForceAlwaysOn"].value)
            self.MW_NBPVoltageAdjust = int(updater["Setup"]["MW_NBPVoltageAdjust"].value)
            self.MW_BIC2200_efficacy_factor = int(updater["Setup"]["MW_BIC2200_efficacy_factor"].value)
            self.MW_NPB_ChargeVoltCorr = int(updater["Setup"]["MW_NPB_ChargeVoltCorr"].value)
            self.MW_BIC_ChargeVoltCorr = int(updater["Setup"]["MW_BIC_ChargeVoltCorr"].value)
            self.MW_BIC_DisChargeVoltCorr = int(updater["Setup"]["MW_BIC_DisChargeVoltCorr"].value)
            self.MW_BIC2200_MaxTemp = int(updater["Setup"]["MW_BIC2200_MaxTemp"].value)
            self.MW_NPB_MaxTemp = int(updater["Setup"]["MW_NPB_MaxTemp"].value)

            self.CBC_devid = int(updater["Setup"]["CBC_devid"].value)
            self.CBC_ipadr = updater["Setup"]["CBC_ipadr"].value
            self.CBC_user = updater["Setup"]["CBC_user"].value
            self.CBC_pass = updater["Setup"]["CBC_pass"].value
            self.CBC_wattdelta = int(updater["Setup"]["CBC_wattdelta"].value)

            self.mPSU_device = updater["Setup"]["mPSU_device"].value
            self.mPSU_interface = int(updater["Setup"]["mPSU_interface"].value)
            self.mPSU_count = int(updater["Setup"]["mPSU_count"].value)
            self.mPSU1_nodeid = int(updater["Setup"]["mPSU1_nodeid"].value)
            self.mPSU2_nodeid = int(updater["Setup"]["mPSU2_nodeid"].value)
            self.mPSU3_nodeid = int(updater["Setup"]["mPSU3_nodeid"].value)
            self.mPSU4_nodeid = int(updater["Setup"]["mPSU4_nodeid"].value)
            self.mPSU_ChargeVoltCorr = int(updater["Setup"]["mPSU_ChargeVoltCorr"].value)
            self.mPSU_VoltageAdjust = int(updater["Setup"]["mPSU_VoltageAdjust"].value)

            self.MeterStopOnConnectionLost = int(updater["Setup"]["MeterStopOnConnectionLost"].value)
            self.GetPowerOption = int(updater["Setup"]["GetPowerOption"].value)
            self.PowerControlmethod = int(updater["Setup"]["PowerControlmethod"].value)

            self.http_schedule_time = int(updater["Setup"]["http_schedule_time"].value)

            self.http_get_option = int(updater["Setup"]["http_get_option"].value)
            self.http_ip_address = updater["Setup"]["http_ip_address"].value
            self.http_ip_port = updater["Setup"]["http_ip_port"].value
            self.http_user = updater["Setup"]["http_user"].value
            self.http_pass = updater["Setup"]["http_pass"].value
            self.http_emlog_meterindex = updater["Setup"]["http_EMLOG_METERINDEX"].value
            self.http_vzl_UUID = updater["Setup"]["http_VZL_UUID"].value
            self.http_iobrogerobject = updater["Setup"]["http_iobrogerobject"].value

            self.lt_devtype = int(updater["Setup"]["lt_devtype"].value)
            self.lt_foreceoffonstartup = int(updater["Setup"]["lt_foreceoffonstartup"].value)
            self.lt_count = int(updater["Setup"]["lt_count"].value)
            self.lt_efficacy_factor = int(updater["Setup"]["lt_efficacy_factor"].value)
            self.lt_MaxTemp = int(updater["Setup"]["lt_MaxTemp"].value)

            self.lt1_device = updater["Setup"]["lt1_device"].value
            self.lt1_address = int(updater["Setup"]["lt1_address"].value)
            self.lt1_maxwatt = int(updater["Setup"]["lt1_maxwatt"].value)

            self.lt2_device = updater["Setup"]["lt2_device"].value
            self.lt2_address = int(updater["Setup"]["lt2_address"].value)
            self.lt2_maxwatt = int(updater["Setup"]["lt2_maxwatt"].value)

            self.lt3_device = updater["Setup"]["lt3_device"].value
            self.lt3_address = int(updater["Setup"]["lt3_address"].value)
            self.lt3_maxwatt = int(updater["Setup"]["lt3_maxwatt"].value)

            self.soyo_device = updater["Setup"]["soyo_device"].value
            self.soyo_maxwatt = int(updater["Setup"]["soyo_maxwatt"].value)
            self.soyo_efficacy_factor = int(updater["Setup"]["soyo_efficacy_factor"].value)

            self.mqttserver = updater["Setup"]["mqttserver"].value
            self.mqttport = int(updater["Setup"]["mqttport"].value)
            self.mqttuser = updater["Setup"]["mqttuser"].value
            self.mqttpass = updater["Setup"]["mqttpass"].value
            self.mqttsubscribe = updater["Setup"]["mqttsubscribe"].value
            self.mqttpublish = int(updater["Setup"]["mqttpublish"].value)
            self.mqttpublishBatWh = updater["Setup"]["mqttpublishBatWh"].value
            self.mqttpublishWATT = updater["Setup"]["mqttpublishWATT"].value
            self.mqttpublishSOC = updater["Setup"]["mqttpublishSOC"].value
            self.mqttpublishBatVolt = updater["Setup"]["mqttpublishBatVolt"].value
            self.mqttpublishWATTCut = int(updater["Setup"]["mqttpublishWATTCut"].value)

            self.mqttaction1topic = updater["Setup"]["mqttaction1topic"].value
            self.mqttaction2topic = updater["Setup"]["mqttaction2topic"].value
            self.mqttaction3topic = updater["Setup"]["mqttaction3topic"].value
            self.mqttaction4topic = updater["Setup"]["mqttaction4topic"].value
            self.mqttaction1payload = updater["Setup"]["mqttaction1payload"].value
            self.mqttaction2payload = updater["Setup"]["mqttaction2payload"].value
            self.mqttaction3payload = updater["Setup"]["mqttaction3payload"].value
            self.mqttaction4payload = updater["Setup"]["mqttaction4payload"].value
            self.mqttaction1name = updater["Setup"]["mqttaction1name"].value
            self.mqttaction2name = updater["Setup"]["mqttaction2name"].value
            self.mqttaction3name = updater["Setup"]["mqttaction3name"].value
            self.mqttaction4name = updater["Setup"]["mqttaction4name"].value

            self.Selected_BMS = int(updater["Setup"]["Selected_BMS"].value)
            self.SASBBMSType = int(updater["Setup"]["SASBBMSType"].value)
            self.SASBBMSAdr = updater["Setup"]["SASBBMSAdr"].value
            self.BMS_device = updater["Setup"]["BMS_device"].value
            self.BMS_daly_use_sinowealth = updater["Setup"]["BMS_daly_use_sinowealth"].value
            self.BMS_minSOC = int(updater["Setup"]["BMS_minSOC"].value)
            self.BMS_RestartSOC = int(updater["Setup"]["BMS_RestartSOC"].value)
            self.BMS_MaxTempMosFet = int(updater["Setup"]["BMS_MaxTempMosFet"].value)
            self.BMS_MaxTemp1 = int(updater["Setup"]["BMS_MaxTemp1"].value)
            self.BMS_MaxTemp2 = int(updater["Setup"]["BMS_MaxTemp2"].value)

            self.Selected_LCD = int(updater["Setup"]["Selected_LCD"].value)
            self.lcdi2cadr = int(updater["Setup"]["lcdi2cadr"].value)

            self.Use_GPIO = int(updater["Setup"]["Use_GPIO"].value)
            self.gpio1 = int(updater["Setup"]["gpio1"].value)
            self.gpio2 = int(updater["Setup"]["gpio2"].value)
            self.gpio3 = int(updater["Setup"]["gpio3"].value)
            self.gpio4 = int(updater["Setup"]["gpio4"].value)

            self.Use_WebServer = int(updater["Setup"]["Use_WebServer"].value)
            self.WSport = int(updater["Setup"]["WSport"].value)
            self.WSipadr = updater["Setup"]["WSipadr"].value
            if self.WSipadr == "":
                try:
                    self.WSipadr = subprocess.check_output(["hostname", "-I"]).decode().split()[0]
                except Exception as e:
                    mylogs.error("EXCEPTION ON GETTING LOCAL IP ADDRESS - USE EMPTY ONE")
                    mylogs.error(str(e))
                    self.WSipadr = ""

            updater["Setup"]["MW_NPB_COUNTER_LAST"].value = str(self.MW_NPB_COUNTER) + "_" + datetime.datetime.now().strftime("%d-%m-%Y, %H:%M")
            updater["Setup"]["MW_BIC_COUNTER_LAST"].value = str(self.MW_BIC_COUNTER) + "_" + datetime.datetime.now().strftime("%d-%m-%Y, %H:%M")
            updater.update_file()

            mylogs.info("-- Main --                  ")
            mylogs.info("ChargerPowerCalcCount:      " + str(self.ChargerPowerCalcCount))
            mylogs.info("DisChargerPowerCalcCount:   " + str(self.DisChargerPowerCalcCount))

            mylogs.info("PowerControlmethod:         " + str(self.PowerControlmethod))
            mylogs.info("Selected_Device_Charger:    " + str(self.Selected_Device_Charger))
            mylogs.info("Selected_Device_DisCharger: " + str(self.Selected_Device_DisCharger))
            mylogs.info("ChargerCurrentDiffHyst:     " + str(self.ChargerCurrentDiffHyst))
            mylogs.info("DisChargerCurrentMin:       " + str(self.DisChargerCurrentMin))
            mylogs.info("MaxChargeWATT:              " + str(self.MaxChargeWATT))
            mylogs.info("MinChargeWATT:              " + str(self.MinChargeWATT))
            mylogs.info("LastChargePower_delta:      " + str(self.LastChargePower_delta))
            mylogs.info("MaxDisChargeWATT:           " + str(self.MaxDisChargeWATT))
            mylogs.info("MinDisChargeWATT:           " + str(self.MinDisChargeWATT))

            mylogs.info("CBC_devid:                  " + str(self.CBC_devid))
            mylogs.info("CBC_wattdelta:              " + str(self.CBC_wattdelta))
            mylogs.info("CBC_ipadr:                  " + self.CBC_ipadr)
            mylogs.info("CBC_user:                   " + self.CBC_user)
            mylogs.info("CBC_pass:                   " + self.CBC_pass)

            mylogs.info("MaxChargeCurrent:           " + str(self.MaxChargeCurrent))
            mylogs.info("MinChargeCurrent:           " + str(self.MinChargeCurrent))
            mylogs.info("ZeroDeltaChargerWATT:       " + str(self.ZeroDeltaChargerWATT))
            mylogs.info("MaxDisChargeCurrent:        " + str(self.MaxDisChargeCurrent))
            mylogs.info("ZeroDeltaDisChargeWATT:     " + str(self.ZeroDeltaDisChargeWATT))

            mylogs.info("LastDisChargePower_delta:   " + str(self.LastDisChargePower_delta))
            mylogs.info("Voltage_ACIN_correction:    " + str(self.Voltage_ACIN_correction))

            mylogs.info("-- PowerMeter --            ")
            mylogs.info("GetPowerOption:             " + str(self.GetPowerOption))
            mylogs.info("MeterDelaytime:             " + str(self.MeterDelaytime))
            mylogs.info("MeterSwapValue:             " + str(self.MeterSwapValue))

            mylogs.info("MeterUpdateChargeCounter:   " + str(self.MeterUpdateChargeCounter))
            mylogs.info("MeterUpdateDisChargeCounter:" + str(self.MeterUpdateDisChargeCounter))
            mylogs.info("MeterStopOnConnectionLost:  " + str(self.MeterStopOnConnectionLost))

            mylogs.info("-- HTTP --                  ")
            mylogs.info("http_schedule_time:         " + str(self.http_schedule_time))
            mylogs.info("http_get_option:            " + str(self.http_get_option))
            mylogs.info("http_ip_address:            " + self.http_ip_address)
            mylogs.info("http_ip_port:               " + self.http_ip_port)
            mylogs.info("http_user:                  " + self.http_user)
            mylogs.info("http_pass:                  " + self.http_pass)
            mylogs.info("http_emlog_meterindex:      " + self.http_emlog_meterindex)
            mylogs.info("http_vzl_UUID:              " + self.http_vzl_UUID)
            mylogs.info("http_iobrogerobject:        " + self.http_iobrogerobject)

            mylogs.info("-- Meanwell --              ")
            mylogs.info("MW_USEDID:                  " + str(self.MW_USEDID))
            mylogs.info("MW_NPB_COUNTER:             " + str(self.MW_NPB_COUNTER))
            mylogs.info("MW_BIC_COUNTER:             " + str(self.MW_BIC_COUNTER))
            mylogs.info("MW_NPB_ChargeVoltCorr:      " + str(self.MW_NPB_ChargeVoltCorr))
            mylogs.info("MW_BIC_ChargeVoltCorr:      " + str(self.MW_BIC_ChargeVoltCorr))
            mylogs.info("MW_BIC_DisChargeVoltCorr:   " + str(self.MW_BIC_DisChargeVoltCorr))
            mylogs.info("MW_BIC2200_MaxTemp:         " + str(self.MW_BIC2200_MaxTemp))
            mylogs.info("MW_BIC2200_ForceAlwaysOn:   " + str(self.MW_BIC2200_ForceAlwaysOn))
            mylogs.info("MW_NBPVoltageAdjust:        " + str(self.MW_NBPVoltageAdjust))
            mylogs.info("MW_BIC2200_efficacy_factor  " + str(self.MW_BIC2200_efficacy_factor))
            mylogs.info("MW_NPB_MaxTemp:             " + str(self.MW_NPB_MaxTemp))

            mylogs.info("-- mPSU --                    ")
            mylogs.info("mPSU_device:                  " + self.mPSU_device)
            mylogs.info("mPSU_count:                   " + str(self.mPSU_count))
            mylogs.info("mPSU1_nodeid:                 " + str(self.mPSU1_nodeid))
            mylogs.info("mPSU2_nodeid:                 " + str(self.mPSU2_nodeid))
            mylogs.info("mPSU3_nodeid:                 " + str(self.mPSU3_nodeid))
            mylogs.info("mPSU4_nodeid:                 " + str(self.mPSU4_nodeid))
            mylogs.info("mPSU_ChargeVoltCorr:          " + str(self.mPSU_ChargeVoltCorr))
            mylogs.info("mPSU_VoltageAdjust:           " + str(self.mPSU_VoltageAdjust))

            mylogs.info("-- Lumentree --             ")
            mylogs.info("Lumentree efficacy_factor   " + str(self.lt_efficacy_factor))
            mylogs.info("Lumentree Count             " + str(self.lt_count))
            mylogs.info("Lumentree lt_MaxTemp        " + str(self.lt_MaxTemp))

            mylogs.info("Lumentree device  1         " + self.lt1_device)
            mylogs.info("Lumentree address 1         " + str(self.lt1_address))
            mylogs.info("Lumentree maxwatt 1         " + str(self.lt1_maxwatt))
            mylogs.info("Lumentree device  2         " + self.lt2_device)
            mylogs.info("Lumentree address 2         " + str(self.lt2_address))
            mylogs.info("Lumentree maxwatt 2         " + str(self.lt2_maxwatt))
            mylogs.info("Lumentree device  3         " + self.lt3_device)
            mylogs.info("Lumentree address 3         " + str(self.lt3_address))
            mylogs.info("Lumentree maxwatt 3         " + str(self.lt3_maxwatt))

            mylogs.info("-- Soyo 1000 --             ")
            mylogs.info("Soyo device                 " + self.soyo_device)
            mylogs.info("Soyo maxwatt                " + str(self.soyo_maxwatt))
            mylogs.info("Soyo efficacy_factor        " + str(self.soyo_efficacy_factor))

            mylogs.info("-- MQTT --                  ")
            mylogs.info("mqttserver:                 " + self.mqttserver)
            mylogs.info("mqttport:                   " + str(self.mqttport))
            mylogs.info("mqttuser:                   " + self.mqttuser)
            mylogs.info("mqttpass:                   " + self.mqttpass)
            mylogs.info("mqttsubscribe:              " + str(self.mqttsubscribe))
            mylogs.info("mqttpublish:                " + str(self.mqttpublish))
            mylogs.info("mqttpublishWATT:            " + str(self.mqttpublishWATT))
            mylogs.info("mqttpublishSOC:             " + str(self.mqttpublishSOC))
            mylogs.info("mqttpublishBatVolt:         " + str(self.mqttpublishBatVolt))
            mylogs.info("mqttpublishWATTCut:         " + str(self.mqttpublishWATTCut))

            mylogs.info("-- BMS --                   ")
            mylogs.info("Selected_BMS:               " + str(self.Selected_BMS))
            mylogs.info("SASBBMSType:                 " + str(self.SASBBMSType))
            mylogs.info("SASBBMSAdr:                 " + str(self.SASBBMSAdr))
            mylogs.info("BMS_device:                 " + str(self.BMS_device))
            mylogs.info("BMS_minSOC:                 " + str(self.BMS_minSOC))
            mylogs.info("BMS_RestartSOC:             " + str(self.BMS_RestartSOC))
            mylogs.info("BMS_MaxTempMosFet:          " + str(self.BMS_MaxTempMosFet))
            mylogs.info("BMS_MaxTemp1:               " + str(self.BMS_MaxTemp1))
            mylogs.info("BMS_MaxTemp2:               " + str(self.BMS_MaxTemp2))

            mylogs.info("-- LCD --                   ")
            mylogs.info("Selected_LCD:               " + str(self.Selected_LCD))
            mylogs.info("lcdi2cadr:                  " + str(self.lcdi2cadr))

            mylogs.info("-- Battery parameter --     ")
            mylogs.info("CellCount:                  " + str(self.CellCount))
            mylogs.info("CellvoltageMax:             " + str(self.CellvoltageMax))
            mylogs.info("CellvoltageMin:             " + str(self.CellvoltageMin))
            mylogs.info("CellvoltageMaxRestart:      " + str(self.CellvoltageMaxRestart))
            mylogs.info("CellvoltageMinRestart:      " + str(self.CellvoltageMinRestart))
            mylogs.info("BatteryTotalWH:             " + str(self.BatteryTotalWH))

            mylogs.info("FixedChargeVoltage:         " + str(self.FixedChargeVoltage))
            mylogs.info("RestartChargevoltage:       " + str(self.RestartChargevoltage))
            mylogs.info("StopMinChargeCurrent:       " + str(self.StopMinChargeCurrent))

            mylogs.info("StopDischargeVoltage:       " + str(self.StopDischargeVoltage))
            mylogs.info("RestartDisChargevoltage:    " + str(self.RestartDisChargevoltage))

            mylogs.info("BatteryVoltageSource:       " + str(self.BatteryVoltageSource))
            mylogs.info("BatteryVoltageCorrection:   " + str(self.BatteryVoltageCorrection))

            mylogs.info("-- WebServer Config --      ")
            mylogs.info("Use_WebServer:              " + str(self.Use_WebServer))
            mylogs.info("WSport:                     " + str(self.WSport))
            mylogs.info("WSipadr:                    " + self.WSipadr)

            mylogs.info("Read config done ...")

        except Exception as e:
            mylogs.error("EXCEPTION READING CONFIG FILE")
            mylogs.error(str(e))
            sys.exit(1)

        return

    def iniwrite(self):
        mylogs.verbose("WRITE CONF FILE")
        updater = ConfigUpdater()
        updater.read(status.configfile)

        updater["Setup"]["MW_NPB_COUNTER"].value = str(cfg.MW_NPB_COUNTER)
        updater["Setup"]["MW_BIC_COUNTER"].value = str(cfg.MW_BIC_COUNTER)
        updater["Setup"]["EstBatteryWh"].value = str(cfg.EstBatteryWh)
        updater["Setup"]["i_changed_my_config"].value = str(cfg.i_changed_my_config)

        updater.update_file()
        return

    def __init__(self):
        self.iniread()
        return


##########EXIT###############################################
def on_exit():
    global status
    try:
        mylogs.info("CLEAN UP ...")
        schedule.clear()  # remove all schedules if exists or not

        # first close external script in case that user wants do do someting with devices
        # WARNING you should know what you are doing !
        if bs_ext != None:
            try:
                status = bs_ext.ext_close(dev, cfg, status)
            except Exception as e:
                mylogs.error("ON EXIT EXCEPTION at EXTERNAL SCRIPT CLOSE")
                mylogs.error(str(e))

        # Shutdown Meter to prevent new messages
        if (cfg.GetPowerOption == 0) or (cfg.mqttpublish == 1):
            if dev.mqttclient != None:
                mylogs.info("CLEAN UP: Shutdown MQTT")
                dev.mqttclient.on_message = ""  # prevent any further message to be proceed
                mqttpublish(1)
                sleep(0.5)
                mqttpublish(1)
                mylogs.info("CLEAN UP: mqtt unsubcribe: " + cfg.mqttsubscribe)
                # Doing it 2 times to be sure we really unsubscribe, ignore error message
                dev.mqttclient.unsubscribe(cfg.mqttsubscribe)
                dev.mqttclient.unsubscribe(cfg.mqttsubscribe)
                dev.mqttclient.disconnect()
                dev.mqttclient.loop_stop()

        try:
            sleep(0.5)  # wait to be sure that mqtt is really down and no new message will be proceed !
            cfg.MW_BIC2200_ForceAlwaysOn = 0  # Prevent BIC will not shutdown
            StartStopOperationCharger(0, 1)
            StartStopOperationDisCharger(0, 1)
        except Exception as e:
            mylogs.error("ON EXIT EXCEPTION at START STOP OPERATION!")
            mylogs.error(str(e))

        #        if (cfg.Selected_Device_Charger == 2):
        #            mylogs.verbose("CONSTANT BASED CHARGER SETUP")
        #            cbc = ChargerConstBased(cfg.CBC_devid, cfg.CBC_ipadr, cfg.CBC_user, cfg.CBC_pass, cfg.loglevel)
        #            cbc.PowerOff()

        # CAN close for 0=bic2200 and 1=NPB
        if dev.mwcandev != None:
            try:
                if cfg.Selected_Device_Charger == 0:  # BIC2200 set to min in case of an error, but should be off already
                    mylogs.info("CLEAN UP: Set BIC2200 to minimum for charge and discharge")
                    dev.mwcandev.BIC_discharge_i(1, cfg.MinDisChargeCurrent)
                    dev.mwcandev.i_out_set(1, cfg.MinChargeCurrent)
                    MW_EEPROM_Counter_INC(0)
                    MW_EEPROM_Counter_INC(1)

                mylogs.info("CLEAN UP: Shutdown MEANWELL DEVICE")
                mylogs.info("Close CAN device")
                dev.mwcandev.can_down()
                if status.MW_EEPromOff == 0:
                    mylogs.info("MEANWELL EEPROM COUNTER  NPB:" + str(cfg.MW_NPB_COUNTER) + "  BIC2200: " + str(cfg.MW_BIC_COUNTER))
            
            except Exception as e:
                mylogs.error("ON EXIT EXCEPTION at MWCANDEV")
                mylogs.error(str(e))

        if dev.mPSU != None:
            try:
                mylogs.info("CLEAN UP: Shutdown mPSU DEVICE")
                mylogs.info("Close device")
                dev.mPSU.network_stop()  # close the bus
            except Exception as e:
                mylogs.error("ON EXIT EXCEPTION at mPSU")
                mylogs.error(str(e))


        if dev.LT1 != None:  # Lumentree
            try:
                mylogs.info("CLEAN UP: Shutdown LUMENTREE DEVICE(s)")
                dev.LT1.lt232_close()
                if dev.LT2 != None:
                    dev.LT2.lt232_close()
                if dev.LT3 != None:
                    dev.LT3.lt232_close()
            except Exception as e:
                mylogs.error("ON EXIT EXCEPTION at LUMENTREE")
                mylogs.error(str(e))

        if dev.soyo != None:  # soyo
            try:            
                mylogs.info("CLEAN UP: Shutdown Soyo DEVICE(s)")
                dev.soyo.soyo485_close()
            except Exception as e:
                mylogs.error("ON EXIT EXCEPTION at SOYO")
                mylogs.error(str(e))

        if dev.jk != None:
            try:
                mylogs.info("CLEAN UP: Shutdown JK BMS")
                dev.jk.jkbms_close()
            except Exception as e:
                mylogs.error("ON EXIT EXCEPTION at JKBMS")
                mylogs.error(str(e))


        if dev.daly != None:
            try:
                mylogs.info("CLEAN UP: Shutdown DALY BMS")
                dev.daly.dalybms_close()
            except Exception as e:
                mylogs.error("ON EXIT EXCEPTION at DALY")
                mylogs.error(str(e))


        if cfg.Selected_LCD == 1:
            printlcd(line1="SCRIPT STOP", line2="REASON UNKNOWN")
            # dev.display.lcd_clear()
            mylogs.info("CLEAN UP: Shutdown LCD/OLED")

        cfg.EstBatteryWh = round(status.EstBatteryWh)
        cfg.iniwrite()

    except Exception as e:
        mylogs.error("ON EXIT EXCEPTION !")
        mylogs.error(str(e))
        cfg.iniwrite()


def handle_exit(signum, frame):
    mylogs.info("SIGNAL TO STOP RECEIVED " + str(signum))
    # sys.exit(0)
    raise (SystemExit)


def CheckPatameter():
    if (cfg.CellvoltageMax > 365) or (cfg.CellvoltageMin < 250):
        mylogs.error("\n\nCELL VOLTAGE TOO HIGH OR TOO LOW! Voltage: " + str(cfg.CellvoltageMin) + " - " + cfg.CellvoltageMax + "\n")
        return 1

    #    if((status.ChargerMainVoltage / cfg.CellCount) != 300):
    #        mylogs.error("\n\nCHARGER DOES NOT FIT FOR YOUR BATTERY, TOO LOW/HIGH VOLTAGE !")
    #        mylogs.error("Charger Main Voltage: " + str(status.ChargerMainVoltage) + " - CellCount: " + str(cfg.CellCount))
    #        return 1

    if (cfg.MW_NPB_COUNTER > 4000000) or (cfg.MW_BIC_COUNTER > 4000000):
        mylogs.error("\n\nMEANWELL DEVICE EEPROM MAX WRITE REACHED! " + " - NPB: " + str(cfg.MW_NPB_COUNTER) + " - BIC: " + str(cfg.MW_BIC_COUNTER) + "\n")
        return 1

    if cfg.BatteryVoltageSource == 0:
        mylogs.error("\n\nNO VOLTAGE SOURCE DEFINED BUT NEEDED !!\n")
        return 1

    if (cfg.MW_BIC2200_ForceAlwaysOn == 1) and ((cfg.Selected_Device_Charger + cfg.Selected_Device_DisCharger) != 0):
        mylogs.error("YOU CAN ONLY USE MW_BIC2200_ForceAlwaysOn WITH BIC2200 CONFIGURED AS CHARGER AND DISCHARGER !")
        mylogs.error("SET MW_BIC2200_ForceAlwaysOn to OFF")
        cfg.MW_BIC2200_ForceAlwaysOn = 0
        return 0

    if cfg.BMS_RestartSOC < cfg.BMS_minSOC:
        mylogs.error("\n\nBMS_RestartSOC needs be be higher or equal than BMS_minSOC\n")
        return 1

    # looks good continue
    mylogs.info("Parameter check OK")
    return 0


def MW_EEPROM_Counter_INC(ChargerDisChargemode, force=0):  # CD = 0: Charger; 1: DisCharger, force for BIC change direction and on/off
    mylogs.debug("MW_EEPROM_Counter_INC Mode: " + str(ChargerDisChargemode))
    if (status.MW_EEPromOff == 1) and (force == 0):
        mylogs.debug("MW_EEPROM_WRITE disabled in Firmware :-)")
        return

    if ChargerDisChargemode == 1:  # DisCharger only BIC
        cfg.MW_BIC_COUNTER += 1
        mylogs.info("MW_EEPROM_Counter_INC BIC2200: " + str(cfg.MW_BIC_COUNTER))

    if ChargerDisChargemode == 0:  # Charger
        if cfg.Selected_Device_Charger == 0:  # BIC2200
            cfg.MW_BIC_COUNTER += 1
            mylogs.info("MW_EEPROM_Counter_INC BIC2200: " + str(cfg.MW_BIC_COUNTER))
        if cfg.Selected_Device_Charger == 1:  # NPB
            cfg.MW_NPB_COUNTER += 1
            mylogs.verbose("MW_EEPROM_Counter_INC NPB: " + str(cfg.MW_NPB_COUNTER))
    return


#####################################################################
#####################################################################
# Callback for GPIO if used
#####################################################################
#####################################################################
def gpio_callback(channel):
    try:
        mylogs.debug("GPIO CALLBACK: " + str(channel))

        if channel == cfg.gpio1:
            mylogs.info("GPIO CALLBACK 1")
            status = bs_ext.ext_gpio1(cfg, status)

        if channel == cfg.gpio2:
            mylogs.info("GPIO CALLBACK 2")
            status = bs_ext.ext_gpio2(cfg, status)

        if channel == cfg.gpio3:
            mylogs.info("GPIO CALLBACK 3")
            status = bs_ext.ext_gpio3(cfg, status)

        if channel == cfg.gpio4:
            mylogs.info("GPIO CALLBACK 4")
            status = bs_ext.ext_gpio4(cfg, status)

    except Exception as e:
        mylogs.error("GPIO CALLBACK EXEPTION !")
        mylogs.error(str(e))
    return


#####################################################################
# Main Status
#####################################################################
def logstatus():
    mylogs.info(
        "-> STATUS: C:"
        + str(status.ChargerEnabled)
        + " D:"
        + str(status.DisChargerEnabled)
        + " | SOC:"
        + str(status.BMSSOC)
        + "%  BattV:"
        + str(status.BatteryVoltage / 100)
        + "V |  Total: "
        + str(status.CurrentTotalWatt)
        + "W  Meter:"
        + str(status.CurrentWattValue)
        + "W  Average: "
        + str(status.CurrentAverageWatt)
        + "W  LOUT:"
        + str(status.LastWattValueUsedinDevice)
        + "W | RCAP: "
        + str(round(status.EstBatteryWh / 1000))
    )
    if status.MW_EEPromOff == 0:
        mylogs.verbose("-> STATUS: BICC: " + str(cfg.MW_BIC_COUNTER) + " - NPBC: " + str(cfg.MW_NPB_COUNTER))


#####################################################################
# LCD routine
#####################################################################
def LCDinit():
    mylogs.info("Init display")
    if cfg.Selected_LCD == 1:
        try:
            dev.display = i2clcd(cfg.lcdi2cadr)
            dev.display.lcd_clear()
        except Exception as e:
            mylogs.error("\n\nEXECETION INIT DISPLAY !\n")
            mylogs.error(str(e))


def printlcd(line1="", line2=""):
    if cfg.Selected_LCD == 0:
        return
    try:
        if line1 == "":
            if status.LastWattValueUsedinDevice > 0:
                line1 = "PW:" + "{:<5}".format(str(status.CurrentWattValue)) + " O:" + str(status.LastWattValueUsedinDevice)
            else:
                line1 = "PW:" + "{:<5}".format(str(status.CurrentWattValue)) + " I:" + str(status.LastWattValueUsedinDevice)

        if line2 == "":
            line2 = "SC:" + "{:<6}".format(str(status.BMSSOC) + "%") + "C:" + str(status.ChargerEnabled) + " D:" + str(status.DisChargerEnabled)

        if cfg.Selected_LCD == 1:
            dev.display.lcd_clear()
            mylogs.debug("LCD: Print LCD")
            dev.display.lcd_display_string(line1, 1)
            dev.display.lcd_display_string(line2, 2)

    except Exception as e:
        mylogs.error("LCD PRINT EXEPTION !")
        mylogs.error(str(e))
    return


#####################################################################
# MQTT publish
#####################################################################
def mqttpublish(cleanup=0):
    if cfg.mqttpublish == 0:
        return
    mylogs.debug("mqtt: publish data to broker")
    try:
        if cleanup == 1:
            lwatt = 0
        else:
            lwatt = status.LastWattValueUsedinDevice + status.ext_lastwattusedindevice
        if cfg.mqttpublishWATTCut > 0:
            if abs(lwatt) <= cfg.mqttpublishWATTCut:
                lwatt = 0

        if cfg.mqttpublishWATT != "":
            dev.mqttclient.publish(cfg.mqttpublishWATT, payload=lwatt, qos=1, retain=True)
        if cfg.mqttpublishBatWh != "":
            dev.mqttclient.publish(cfg.mqttpublishBatWh, payload=round(status.EstBatteryWh / 1000), qos=1, retain=True)
        if cfg.mqttpublishSOC != "":
            dev.mqttclient.publish(cfg.mqttpublishSOC, payload=status.BMSSOC, qos=1, retain=True)
        if cfg.mqttpublishBatVolt != "":
            dev.mqttclient.publish(
                cfg.mqttpublishBatVolt,
                payload=status.BatteryVoltage,
                qos=1,
                retain=True,
            )
    except Exception as e:
        mylogs.error("MQTT PUBLISH EXEPTION !")
        mylogs.error(str(e))
    return


def externalaction(nr, cleanup=0):
    mylogs.info("External Action: " + str(nr))
    try:
        if nr == "1":
            status = bs_ext.ext_action_1(cfg, status)
        if nr == "2":
            status = bs_ext.ext_action_2(cfg, status)
        if nr == "3":
            status = bs_ext.ext_action_3(cfg, status)
        if nr == "4":
            status = bs_ext.ext_action_4(cfg, status)
    except Exception as e:
        mylogs.error("EXT ACTION EXEPTION !")
        mylogs.error(str(e))
    return


def mqttactionpublish(nr, cleanup=0):
    if cfg.mqttpublish == 0:
        return
    mylogs.info("Action publish: " + str(nr))
    try:
        if nr == "1":
            dev.mqttclient.publish(cfg.mqttaction1topic, payload=cfg.mqttaction1payload, qos=0, retain=True)
        if nr == "2":
            dev.mqttclient.publish(cfg.mqttaction2topic, payload=cfg.mqttaction2payload, qos=0, retain=True)
        if nr == "3":
            dev.mqttclient.publish(cfg.mqttaction3topic, payload=cfg.mqttaction3payload, qos=0, retain=True)
        if nr == "4":
            dev.mqttclient.publish(cfg.mqttaction4topic, payload=cfg.mqttaction4payload, qos=0, retain=True)
    except Exception as e:
        mylogs.error("MQTT PUBLISH EXEPTION !")
        mylogs.error(str(e))
    return


#####################################################################
# BMS Section
#####################################################################
def GetBMSData():
    mylogs.debug("GetBMSData entry:")
    if cfg.Selected_BMS == 0:  # disabled return always full for further checks, you should really use a SOC methode !
        status.BMSSOC = 100
        status.BMSConnectionLost = 0
        return status.BMSSOC

    # Software BMS, calculate form DC Voltage, not very exact yet ;-)
    # this works only if the EstBh calculation working almost correctly
    if cfg.Selected_BMS == 1:
        status.BMSVoltage = 0
        status.BMSCurrent = 0

        SocVal = round((status.EstBatteryWh / cfg.BatteryTotalWH) * 100)

        """
        if(status.BatteryVoltage < cfg.CellCount * cfg.CellvoltageMin):   SocVal =   0
        if(status.BatteryVoltage > cfg.CellCount * 3.05              ):   SocVal =  10
        if(status.BatteryVoltage > cfg.CellCount * 3.10              ):   SocVal =  20
        if(status.BatteryVoltage > cfg.CellCount * 3.20              ):   SocVal =  30
        if(status.BatteryVoltage > cfg.CellCount * 3.22              ):   SocVal =  40
        if(status.BatteryVoltage > cfg.CellCount * 3.25              ):   SocVal =  50
        if(status.BatteryVoltage > cfg.CellCount * 3.27              ):   SocVal =  60
        if(status.BatteryVoltage > cfg.CellCount * 3.29              ):   SocVal =  70
        if(status.BatteryVoltage > cfg.CellCount * 3.32              ):   SocVal =  80
        if(status.BatteryVoltage > cfg.CellCount * 3.35              ):   SocVal =  90
        if(status.BatteryVoltage > cfg.CellCount * cfg.CellvoltageMax):   SocVal = 100
        """

        status.BMSSOC = SocVal
        status.BMSConnectionLost = 0
        return status.BMSSOC

    try:
        # Read BMS, ST return need to be the same for all BMS devices !
        # JKBMS read
        if cfg.Selected_BMS == 2:
            ST = dev.jk.jkbms_read()

        # DALYBMS read
        if cfg.Selected_BMS == 3:
            ST = dev.daly.dalybms_read()

        # SASBBMS read
        if cfg.Selected_BMS == 100:
            ST = dev.sasb.bms_read()

        BMSstatus.CellCount = ST[0]
        for i in range(ST[0]):
            BMSstatus.BMSCellVoltage[i] = ST[i + 1]

        i = ST[0] + 1  # first is the cellscount and cells
        BMSstatus.BMSTemp_Mosfet = ST[i]
        BMSstatus.BMSTemp1 = ST[i + 1]
        BMSstatus.BMSTemp2 = ST[i + 2]
        BMSstatus.BMSTemp3 = ST[i + 3]
        BMSstatus.BMSTemp4 = ST[i + 4]
        BMSstatus.BMSVoltage = ST[i + 5]
        BMSstatus.BMSCurrent = ST[i + 6]
        BMSstatus.BMSSOC = ST[i + 7]

        status.BMSVoltage = BMSstatus.BMSVoltage
        status.BMSCurrent = BMSstatus.BMSCurrent
        status.BMSSOC = BMSstatus.BMSSOC

        CVolt = ""
        mylogs.debug("Cellcount: " + str(BMSstatus.CellCount))
        for i in range(BMSstatus.CellCount):
            CVolt = CVolt + "C" + str(i) + ": " + str(BMSstatus.BMSCellVoltage[i] / 1000) + " "
            mylogs.debug("BMS: CellVolt" + str(i) + ": " + str(BMSstatus.BMSCellVoltage[i] / 1000))
        mylogs.debug("BMS: Temp_Fet : " + str(BMSstatus.BMSTemp_Mosfet))
        mylogs.debug("BMS: Temp_1   : " + str(BMSstatus.BMSTemp1))
        mylogs.debug("BMS: temp_2   : " + str(BMSstatus.BMSTemp2))
        mylogs.debug("BMS: BatVolt  : " + str(BMSstatus.BMSVoltage / 100))
        mylogs.debug("BMS: Current  : " + str(BMSstatus.BMSCurrent / 100))
        mylogs.debug("BMS: BMSSOC   : " + str(BMSstatus.BMSSOC))

        mylogs.info("BMSData: " + str(BMSstatus.BMSVoltage / 100) + "V  " + str(BMSstatus.BMSCurrent / 100) + "A  " + str(BMSstatus.BMSSOC) + "%  " + CVolt)
        status.BMSConnectionLost = 0
        return status.BMSSOC

    except Exception as e:
        mylogs.error("BMS READ ERROR. LOST CONNECTION -> STOP ALL DEVICES")
        mylogs.error(str(e))
        status.BMSSOC = 0
        # Disable charger and discharger and stop further operation until BMS OK
        StartStopOperationCharger(0, 1)
        StartStopOperationDisCharger(0, 1)
        status.BMSConnectionLost = status.BMSConnectionLost + 1
        # could not read BMS -> exit or restert
        if status.BMSConnectionLost >= 5:
            mylogs.error("BMS ERROR >= 5 - Exit")
            """
            p = os.path.dirname(__file__)
            subprocess.Popen([p + '/BSstart.py',0], start_new_session=True)
            """
            sys.exit(1)

        return

    mylogs.error("UNKNOWN BMS USED ! Check Configuration !")
    sys.exit(1)
    return


#####################################################################
#####################################################################
#####################################################################
# Setup Operation mode of charger
def StartStopOperationCharger(val, force=0):
    global status

    mylogs.verbose("StartStopOperationCharger entry: " + str(val) + " Force: " + str(force))

    if status.ChargerEnabled == 0:
        val = 0

    if status.BMSConnectionLost != 0:
        mylogs.warning("StartStopOperationDisCharger: BMS connection lost !")
        val = 0

    if cfg.MW_BIC2200_ForceAlwaysOn == 1:
        if (status.BICChargeDisChargeMode == 1) and (val == 0) and (force == 0):
            mylogs.verbose("StartStopOperationCharger: Always on BIC Mode already set to Discharge. Nothing to do here")
            return
        else:
            mylogs.verbose("StartStopOperationCharger: BIC Mode: " + str(status.BICChargeDisChargeMode))

    # if the Battery is not totally empty anymore, start Discharging
    if (status.BatteryEMPTY == 1) and (status.BatteryVoltage >= cfg.RestartDisChargevoltage):
        mylogs.info(
            "StartStopOperationCharger: Battery Discharging allowed again. Current Volatge: "
            + str(status.BatteryVoltage / 100)
            + " (Restart Voltage: "
            + str(cfg.RestartDisChargevoltage / 100)
            + ")"
        )
        status.BatteryEMPTY = 0

    # if the Battery is not full anymore, start recharging
    if (status.BatteryFULL == 1) and (status.BatteryVoltage <= cfg.RestartChargevoltage):
        mylogs.info(
            "StartStopOperationCharger: Battery charging allowed again. Current Volatge: "
            + str(status.BatteryVoltage / 100)
            + " (Restart Voltage: "
            + str(cfg.RestartChargevoltage / 100)
            + ")"
        )
        status.BatteryFULL = 0

    # Battery is full, stop charing and wait for discharge
    if (
        (status.BatteryFULL == 0)
        and (status.ChargerStatus == 1)
        and (status.LastChargerGetCurrent <= cfg.StopMinChargeCurrent)
        and ((status.BatteryVoltage + 10) > cfg.FixedChargeVoltage)
    ):  # and (status.BMSSOC > 97)):
        mylogs.info(
            "StartStopOperationCharger: Battery Full ! - Charging current too small: " + str(status.LastChargerGetCurrent) + " - Min: " + str(cfg.StopMinChargeCurrent)
        )
        status.BatteryFULL = 1
        force = 2  # force stop charging, 2 if BIC is used with always on
        # Set to est. max of installed battery
        status.EstBatteryWh = cfg.BatteryTotalWH

    if status.BatteryFULL == 1:
        mylogs.info("StartStopOperationCharger: Battery Full ! - Nothing to do ... - Time for Idleling ;-)")
        val = 0

    Newval = val  # used for calculation later

    if force == 0:  # if force = 1, proceeed without any logic
        if (status.ChargerStatus == 0) and (val == 0):
            mylogs.verbose("StartStopOperationCharger already off mode")
            return  # DisCharger already off, can stop here

        # Check if we need to set the new value to the Charger
        p = abs((status.LastWattValueUsedinDevice - status.ZeroImportWatt) - val)  # was +

        if (val != 0) and (p <= cfg.LastChargePower_delta) and (status.MaxChargeCurrentChange == 0):
            mylogs.info("No change of Charger output, Delta is: " + str(p) + "  - Set to :" + str(cfg.LastChargePower_delta))
            return
        else:
            status.MaxChargeCurrentChange = 0
            if val != 0:
                mylogs.info("Change of Charger output, Delta is: " + str(p) + "  - Set to :" + str(cfg.LastChargePower_delta))

        status.ZeroImportWatt = 0
        SetPowerValArray(cfg.ChargerPowerCalcCount, Newval)
        if val != 0:
            if cfg.ZeroDeltaChargerWATT > 0:
                if val < cfg.ZeroDeltaChargerWATT:
                    Newval = val + cfg.ZeroDeltaChargerWATT
                    status.ZeroImportWatt = cfg.ZeroDeltaChargerWATT
                mylogs.info("ZEROImport: Meter: " + str(val) + " -> ZeroWatt: " + str(Newval) + " (Delta: " + str(cfg.ZeroDeltaChargerWATT) + ")")

    status = bs_ext.ext_charger_set(Newval, force, dev, cfg, status)

    if cfg.Selected_Device_Charger <= 1:  # BIC and NPB-abc0
        # try to set the new ChargeCurrent if possible
        Charger_Device_Set(Newval, force)
        return

    if cfg.Selected_Device_Charger == 2:  # ConstantBasedCharger
        status.LastWattValueUsedinDevice = 0  # prevent wrong calulation
        Const_Based_Charger_Set(Newval, force)
        return

    if cfg.Selected_Device_Charger == 10:  # mPSU
        Charger_Device_Set(Newval, force)
        return

    if cfg.Selected_Device_Charger == 255:  # Simulator
        status.LastWattValueUsedinDevice = 0  # prevent wrong calulation
        mylogs.info("Simulator Charger set to: " + str(Newval) + "W")
        return

    mylogs.error("Charger type not supported yet")
    sys.exit(1)
    return


def StartStopOperationDisCharger(val, force=0):
    global status

    mylogs.verbose("StartStopOperationDisCharger entry: " + str(val) + " Force: " + str(force))

    if status.DisChargerEnabled == 0:
        mylogs.verbose("StartStopOperationDisCharger: DisCharger disabled !")
        val = 0

    if status.BMSConnectionLost != 0:
        mylogs.warning("StartStopOperationDisCharger: BMS connection lost !")
        val = 0

    if (cfg.MW_BIC2200_ForceAlwaysOn == 1) and (status.BICChargeDisChargeMode == 0) and (val == 0) and (force == 0):
        mylogs.verbose("StartStopOperationDisCharger: Always on BIC Mode already set to Charge. Nothing to do here")
        return

    # if the Battery is not full anymore, start recharging
    if (status.BatteryFULL == 1) and (status.BatteryVoltage <= cfg.RestartChargevoltage):
        mylogs.info(
            "StartStopOperationDisCharger: Battery charging allowed again. Current Volatge: "
            + str(status.BatteryVoltage / 100)
            + " (Restart Voltage: "
            + str(cfg.RestartChargevoltage / 100)
            + ")"
        )
        # BatterFullSpecialOperation(0)
        status.BatteryFULL = 0

    # if the Battery is not totally empty anymore, start Discharging
    if (status.BatteryEMPTY == 1) and (status.BatteryVoltage >= cfg.RestartDisChargevoltage) and (status.BMSSOC >= cfg.BMS_RestartSOC):
        mylogs.info(
            "StartStopOperationDisCharger: Battery Discharging allowed again. Current Volatge: "
            + str(status.BatteryVoltage / 100)
            + " (Restart Voltage: "
            + str(cfg.RestartDisChargevoltage / 100)
            + ")"
        )
        status.BatteryEMPTY = 0

    # Battery is empty, stop Discharing and wait for charging
    # Do not discharge any further if SOC or voltage is lower than specified
    if ((status.BatteryVoltage > 0) and (status.BatteryVoltage <= cfg.StopDischargeVoltage)) or (status.BMSSOC <= cfg.BMS_minSOC):
        status.BatteryEMPTY = 1
        # Set EstBatteryWh to 0, because for this schript the Battery is empty
        status.EstBatteryWh = 0

    if status.BatteryEMPTY == 1:
        mylogs.info("StartStopOperationDisCharger: Battery EMPTY ! Battery Voltage: " + str(status.BatteryVoltage / 100) + " - SOC: " + str(status.BMSSOC))
        val = 0

    # Check if Battery Volatge is online, if not try to disable discharger
    if status.BatteryVoltage == 0:
        mylogs.error("StartStopOperationDisCharger: Battery Voltage can not be read. Battery Voltage: 0")
        val = 0

    Newval = val  # used for calculation
    if force == 0:  # if force = 1, proceeed without any logic
        # for BIC always on proceed with 0 to check status
        if (status.DisChargerStatus == 0) and (val == 0):
            mylogs.verbose("StartStopOperationDisCharger: Already off mode")
            return  # DisCharger already off, can stop here

        # Check if we need to set the new value to the DisCharger
        p = abs((status.LastWattValueUsedinDevice + status.ZeroExportWatt) - val)

        if (val != 0) and (p <= cfg.LastDisChargePower_delta):  # 0:must be processed
            mylogs.info(
                "No change of DisCharger. Delta is: "
                + str(p)
                + " (of: "
                + str(cfg.LastDisChargePower_delta)
                + ") - Last Value: "
                + str(status.LastWattValueUsedinDevice)
                + " (ZeroExport: "
                + str(cfg.ZeroDeltaDisChargeWATT)
                + ") - New: "
                + str(val)
            )
            # status.actchargercounter = 1 #Reset counter to 1
            return
        else:
            if val != 0:
                mylogs.info(
                    "Change of DisCharger. Delta is: "
                    + str(p)
                    + " (of: "
                    + str(cfg.LastDisChargePower_delta)
                    + ") - Last Value: "
                    + str(status.LastWattValueUsedinDevice)
                    + " (ZeroExport: "
                    + str(cfg.ZeroDeltaDisChargeWATT)
                    + ") - New: "
                    + str(val)
                )

        status.ZeroExportWatt = 0
        SetPowerValArray(cfg.DisChargerPowerCalcCount, val)
        if val != 0:
            if cfg.ZeroDeltaDisChargeWATT != 0:  # 03062024 >0
                if val > cfg.ZeroDeltaDisChargeWATT:
                    Newval = val - cfg.ZeroDeltaDisChargeWATT
                    status.ZeroExportWatt = cfg.ZeroDeltaDisChargeWATT
                    mylogs.info("ZEROExport: Meter: " + str(val) + " -> ZeroWatt: " + str(Newval) + " (Delta: " + str(cfg.ZeroDeltaDisChargeWATT) + ")")

    status = bs_ext.ext_discharger_set(Newval, force, dev, cfg, status)

    # Which Device used
    mylogs.debug("StartStopOperationDisCharger: " + str(Newval))
    if cfg.Selected_Device_DisCharger == 0:  # Meanwell BIC-2200
        DisCharger_BIC2200_Set(Newval, force)
        return

    if cfg.Selected_Device_DisCharger == 1:  # Lumentree
        DisCharger_Lumentree_Set(Newval, force)
        return

    if cfg.Selected_Device_DisCharger == 2:  # soyo
        DisCharger_Soyo_Set(Newval, force)
        return

    if cfg.Selected_Device_DisCharger == 255:  # Simulator
        mylogs.info("Simulator DisCharger set to: " + str(Newval) + "W")
        status.LastWattValueUsedinDevice = 0
        # prevent wrong calulation
        return

    mylogs.warning("DisCharger type not supported yet")
    return


#####################################################################
#####################################################################
#####################################################################
# ConstBasedCharger
def Const_Based_Charger_Set(val, force):
    try:
        mylogs.debug("Const_Based_Charger_Set entry - value: " + str(val) + " Force: " + str(force))

        Newval = (-1) * val
        # Only start if val is a lot bigger than MaxChargeWATT
        if (Newval != 0) and ((cfg.MaxChargeWATT + cfg.CBC_wattdelta) < Newval):
            if status.ChargerStatus == 0:
                mylogs.debug("Const_Based_Charger_Set try to set ON")
                r = cbc.PowerOn()
                if r == 1:
                    status.ChargerStatus = 1
                    sleep(0.3)  # wait until BMS shows the current
                    mylogs.verbose("Const_Based_Charger_Set to ON")
                else:
                    mylogs.error("Const_Based_Charger_Set ON ERROR: CAN NOT SET OUTPUT !")

        else:  # stop charging if smaller than MaxChargeWATT
            if (Newval < cfg.MaxChargeWATT) or force:
                mylogs.verbose("Const_Based_Charger_Set to OFF")
                if status.ChargerStatus == 1:
                    r = cbc.PowerOff()
                    if r == 0:
                        status.ChargerStatus = 0
                        status.LastWattValueUsedinDevice = 0
                    else:
                        mylogs.error("Const_Based_Charger_Set OFF ERROR: CAN NOT SET OUTPUT !")

                status.LastWattValueUsedinDevice = 0
                status.LastChargerGetCurrent = 0  # needed for detection Battery full only from Batteryvoltage

        if status.ChargerStatus == 1:
            sleep(0.3)
            GetBMSData()  # Need to know the current for the battery
            status.LastWattValueUsedinDevice = int((BMSstatus.BMSCurrent * BMSstatus.BMSVoltage) / -10000)
            status.LastChargerGetCurrent = BMSstatus.BMSCurrent
            if status.LastWattValueUsedinDevice == 0:  # is off or no BMS available, assume LastWattValueUsedinDevice
                status.LastWattValueUsedinDevice = (-1) * cfg.MaxChargeWATT
                status.LastChargerGetCurrent = 0  # needed for detection Battery full only from Batteryvoltage, 0 to ignore and look only to voltage

        mylogs.verbose("Const_Based_Charger_Set: Output: " + str(status.LastWattValueUsedinDevice) + " New current: " + str(status.LastChargerGetCurrent))

    except Exception as e:
        mylogs.error("Const_Based_Charger_Set: EXEPTION !")
        mylogs.error(str(e))

    return val


#####################################################################
#####################################################################
#####################################################################
# Operation ON/OFF of devices Meanwell / mPSU
def StartStopOperationDevice(val, CD, force=0):
    try:
        mylogs.verbose("StartStopOperationDevice entry - value: " + str(val) + " Force: " + str(force))
        # read current status from device

        if cfg.Selected_Device_Charger <= 1:  # BIC, NPB
            opmode = dev.mwcandev.operation(0, 0)

            if (cfg.MW_BIC2200_ForceAlwaysOn == 1) and (opmode == 1) and ((force == 0) or (force == 2)):  # force=2 is for BIC2200 always on if battary full
                mylogs.verbose("StartStopOperationDevice: BIC ALWAYS ON - nothing to do")
                return 1

        if cfg.Selected_Device_Charger == 10:  # mPSU
            opmode = dev.mPSU.operation(0, 0, cfg.mPSU1_nodeid)

        mylogs.debug("StartStopOperationDevice: Operation mode: " + str(opmode))
        if val == 0:  # set to OFF
            if (opmode != 0) or (force == 1):

                if cfg.Selected_Device_Charger <= 1:  # BIC, NPB
                    dev.mwcandev.operation(1, 0)
                    mylogs.verbose("Meanwell: Operation mode set to: OFF")
                    MW_EEPROM_Counter_INC(CD)

                if cfg.Selected_Device_Charger == 10:  # mPSU
                    opmode = dev.mPSU.operation(1, 0, cfg.mPSU1_nodeid)

                sleep(0.2)
            else:
                mylogs.verbose("StartStopOperationDevice: Operation mode already OFF")
        else:  # set to ON
            if (opmode != 1) or (force == 1):

                if cfg.Selected_Device_Charger <= 1:  # BIC, NPB
                    dev.mwcandev.operation(1, 1)
                    mylogs.verbose("Meanwell: Operation mode set to: ON")
                    MW_EEPROM_Counter_INC(CD)

                if cfg.Selected_Device_Charger == 10:  # mPSU
                    opmode = dev.mPSU.operation(1, 1, cfg.mPSU1_nodeid)

                sleep(0.2)
            else:
                mylogs.verbose("StartStopOperationDevice: Operation mode already ON")

    except Exception as e:
        mylogs.error("StartStopOperationDevice: EXEPTION !")
        mylogs.error(str(e))
        if dev.mwcandev != None:
            # dev.mwcandev.can0.flush_tx_buffer() #flush buffer to clear message queue
            dev.mwcandev.can_restart()

    return val


def Charger_Voltage_controller(newCout):
    # -1 712  8
    # -2 628 84
    # -3 528 100
    # -4 452 76
    # -5 373 79
    # -6 310 63
    # -7 233 77
    # -8 162 71
    # -9 0   162

    # return -1 # not implemented now
    mylogs.verbose("Charger_Voltage_controller - New current: " + str(newCout))

    if cfg.Selected_Device_Charger == 1:  # NPB
        mylogs.debug("Charger_Voltage_controller - Proceed")
        if cfg.MW_NBPVoltageAdjust == 0:
            mylogs.verbose("Charger_Voltage_controller - DISABLED for NPB")
            return -1

        # We only do this voltage charge adjust if EEPROM Write is OFF
        if status.MW_EEPromOff == 0:
            mylogs.error("Charger_Voltage_controller - EEPROM WRITE IS NOT DISABLED - STOP")
            return -1

        rval = dev.mwcandev.v_out_set(0, 0)
        sleep(0.1)

        defaultvoltage = status.MW_ChargeVoltage

    elif cfg.Selected_Device_Charger == 10:  # mPSU
        mylogs.debug("Charger_Voltage_controller - Proceed")
        if cfg.mPSU_VoltageAdjust == 0:
            mylogs.verbose("Charger_Voltage_controller - DISABLED for mPSU")
            return -1

        rval = dev.mPSU.voltage_out_rw(0, 0, cfg.mPSU1_nodeid)
        sleep(0.1)

        defaultvoltage = status.mPSU_ChargeVoltage

    else:
        mylogs.verbose("Charger_Voltage_controller - Only for selected Chargers")
        return -1

    if newCout == 0:
        mylogs.verbose("Charger_Voltage_controller - Disable output")
        return -1

    if newCout >= cfg.MinChargeCurrent:
        NewVoltage = defaultvoltage
    else:
        diffCurrent = newCout - status.LastChargerGetCurrent
        if abs(diffCurrent) < 80:
            mylogs.info("Charger_Voltage_controller - DIFFCURRENT too small: " + str(diffCurrent))
            return 0
        else:
            mylogs.info("Charger_Voltage_controller - DIFFCURRENT: " + str(diffCurrent))

        if diffCurrent > 0:
            diffVolt = 1  # increase voltage by 0.01V
        else:
            diffVolt = -1  # decrease voltage by 0.01V

        mylogs.info("Charger_Voltage_controller - DIFFVOLT: " + str(diffVolt))

        if (rval - 10) > status.ChargerVoltage:
            NewVoltage = status.ChargerVoltage + diffVolt
        else:
            NewVoltage = rval + diffVolt

    if rval != NewVoltage:
        mylogs.info("Charger_Voltage_controller - NEW SET Voltage to: " + str(NewVoltage))

        if cfg.Selected_Device_Charger == 1:  # NPB
            mylogs.debug("Charger_Voltage_controller - NEW SET Voltage to MW NPB: " + str(NewVoltage))
            dev.mwcandev.v_out_set(1, NewVoltage)
            MW_EEPROM_Counter_INC(1)
            return 1

        if cfg.Selected_Device_Charger == 10:  # mPSU
            mylogs.debug("Charger_Voltage_controller - NEW SET Voltage to mPSU: " + str(NewVoltage))
            dev.mPSU.voltage_out_rw(1, NewVoltage, cfg.mPSU1_nodeid)
            return 1
    else:
        mylogs.verbose("Charger_Voltage_controller - Already SET Voltage to: " + str(NewVoltage))
        return 1


def Charger_Device_Set(val, force=0):
    try:
        if cfg.Selected_Device_Charger <= 1:  # NPB
            if dev.mwcandev == None:
                mylogs.error("Charger_Device_Set mwcandev not exists")
                return

        if cfg.Selected_Device_Charger == 10:  # mPSU
            if dev.mPSU == None:
                mylogs.error("Charger_Device_Set mPSU not exists")
                return

        mylogs.verbose("Charger_Device_Set entry - value: " + str(val) + " Force: " + str(force))

        # For BIC set Charge mode first
        if cfg.Selected_Device_Charger == 0:  # BIC2200
            status.BICChargeDisChargeMode = dev.mwcandev.BIC_chargemode(0, 0)
            if status.BICChargeDisChargeMode == 1:
                mylogs.verbose("Charger_Device_Set: Try to set BIC2200 to Charge Mode")
                # if shutdown, we dont have to change it to charge mode val = 0 and force =1
                # if Battery full but shortly switched to discharge, we set charge again, otherwise it would discharge
                if ((val != 0) and (force == 0)) or (status.BatteryFULL == 1):
                    mylogs.info("Charger_Device_Set: Set BIC2200 to Charge Mode")
                    dev.mwcandev.BIC_chargemode(1, 0)  # set BIC to Chargemode
                    sleep(0.2)
                    status.BICChargeDisChargeMode = dev.mwcandev.BIC_chargemode(0, 0)
                    MW_EEPROM_Counter_INC(0, 1)
            else:
                mylogs.verbose("Charger_Device_Set: BIC2200 already in Charge Mode")

        # read voltage and current from BIC / NPB device
        if cfg.Selected_Device_Charger <= 1:  # BIC NPB
            vout = dev.mwcandev.v_out_read()

        if cfg.Selected_Device_Charger == 10:  # mPSU
            vout = dev.mPSU.voltage_read(cfg.mPSU1_nodeid)

        sleep(0.05)
        status.ChargerVoltage = vout

        # Calculate current for meanwell + or - to the actual power from PV / Grid
        # *-10000 --> Vout and iout value is *100 --> 2x100 = 10000
        # charging/discharging current in *100 for meanwell --> e.g. 2600 = 26A

        Current = (val * -10000) / vout
        IntCurrent = int(Current)

        if IntCurrent >= status.MaxChargeCurrent:
            IntCurrent = status.MaxChargeCurrent

        # NPB device has a minimal charge current
        # Stop if this value is reached or allow take power from grid to charge
        if IntCurrent <= cfg.MinChargeCurrent:
            # Check if we can lower the voltage to reduce current, only for NPB
            if Charger_Voltage_controller(IntCurrent) == -1:
                mylogs.info("Charger_Device_Set: Current too small - " + str(IntCurrent) + " - MinCurrent: " + str(cfg.MinChargeCurrent) + " -> Device OFF")
                IntCurrent = 0
                OPStart = False
            else:
                IntCurrent = cfg.MinChargeCurrent
                mylogs.info("Charger_Device_Set: Current / Voltage adapted")
                OPStart = True

        else:  # Reset to standard voltage
            Charger_Voltage_controller(IntCurrent)

        if IntCurrent != status.LastChargerSetCurrent:
            if (status.actchargercounter >= cfg.MeterUpdateChargeCounter) or (force == 1):
                mylogs.info("Charger_Device_Set: >>>> Set new current to: " + str(IntCurrent) + "  (Last current set: " + str(status.LastChargerSetCurrent) + ") <<<<")

                if IntCurrent == 0:
                    # Probably no need to set since device will be set to OFF mode for NBP, but BIC needs to be set to Min 0 = MinChargeCurrent by lib
                    if cfg.MW_BIC2200_ForceAlwaysOn == 1:  # only for BIC in always on mode, set to MinChargeCurrent since 0 is not possible
                        mylogs.info("Charger_Device_Set: BIC-2200 SET IntCurrent = 0 = MinChargerCurrent")
                        c = dev.mwcandev.i_out_set(1, 0)  # (1,IntCurrent)
                        MW_EEPROM_Counter_INC(0)
                        sleep(0.2)
                    else:
                        mylogs.info("Charger_Device_Set: IntCurrent = 0 - Do not set -> Device will be set to OFF")

                    status.LastChargerSetCurrent = IntCurrent
                    OPStart = False  # device start
                else:
                    if (status.LastChargerGetCurrent < (status.LastChargerSetCurrent - 50)) and (IntCurrent > status.LastChargerGetCurrent) and (status.BMSSOC > 97):
                        mylogs.info(
                            "Charger_Device_Set: >>>> NO SET -> BATTERY ALMOST FULL: "
                            + str(IntCurrent)
                            + " (Last current GET: "
                            + str(status.LastChargerGetCurrent)
                            + " ->  Last current SET: "
                            + str(status.LastChargerSetCurrent)
                            + " <<<<"
                        )
                        OPStart = True  # device start or continue
                    else:
                        mylogs.info("Charger_Device_Set: SET NEW CURRENT TO: " + str(IntCurrent))

                        if cfg.Selected_Device_Charger <= 1:  # BIC NPB
                            c = dev.mwcandev.i_out_set(1, IntCurrent)
                            MW_EEPROM_Counter_INC(0)

                        if cfg.Selected_Device_Charger == 10:  # mPSU
                            c = dev.mPSU.current_out_rw(1, IntCurrent, cfg.mPSU1_nodeid)

                        status.LastChargerSetCurrent = IntCurrent
                        OPStart = True  # device start or continue
                        # wait some time to set the currunt in the device to read out the actual value later
                        sleep(0.2)

                status.actchargercounter = 1  # Reset counter to 1
            else:
                mylogs.verbose("Charger_Device_Set: Wait for next change: " + str(status.actchargercounter) + "  of: " + str(cfg.MeterUpdateChargeCounter))
                status.actchargercounter += 1
                if status.ChargerStatus == 0:  # do not change the current status
                    OPStart = False
                else:
                    OPStart = True
        else:
            if IntCurrent != 0:
                mylogs.verbose("Charger_Device_Set: No New current to set. Last current: " + str(status.LastChargerSetCurrent))
                OPStart = True  # device start or continue

        # IF Bic uses always on OPstart True
        if (cfg.MW_BIC2200_ForceAlwaysOn == 1) and (force != 1):
            OPStart = True

        # try to set the new ChargeCurrent if possible
        if OPStart == True:  # if true start mw device
            mylogs.verbose("Charger_Device_Set: OPSTART TRUE : Start Meanwell Device")
            status.ChargerStatus = 1
            StartStopOperationDevice(1, 0, force)
        else:
            mylogs.verbose("OPSTART FALSE: Stop Meanwell Device")
            status.ChargerStatus = 0
            status.ZeroImportWatt = 0
            StartStopOperationDevice(0, 0, force)

        # wait to read the current after MW starts to get a value != 0
        # if 0 returns Battery is full, checked in StartStopCharger
        if cfg.Selected_Device_Charger <= 1:  # BIC NPB
            status.LastChargerGetCurrent = dev.mwcandev.i_out_read()

        if cfg.Selected_Device_Charger == 10:  # mPSU
            status.LastChargerGetCurrent = dev.mPSU.current_read(cfg.mPSU1_nodeid)

        NewVal = int((status.LastChargerGetCurrent * vout) / 10000)
        mylogs.info(
            "Charger_Device_Set INFO: BVout:"
            + str(vout / 100)
            + ":V: Iout:"
            + str(status.LastChargerGetCurrent / 100)
            + ":A: ICalc:"
            + str(IntCurrent / 100)
            + ":A: ILastSet:"
            + str(status.LastChargerSetCurrent / 100)
            + ":A - GET ACT: "
            + str(NewVal)
            + "W  (C:"
            + str(status.actchargercounter)
            + "-"
            + str(cfg.MeterUpdateChargeCounter)
            + ")"
        )
        status.LastWattValueUsedinDevice = NewVal * (-1)

    except Exception as e:
        mylogs.error("Charger_Device_Set: EXEPTION !")
        mylogs.error(str(e))
        if dev.mwcandev != None:
            # dev.mwcandev.can0.flush_tx_buffer() #flush buffer to clear message queue
            dev.mwcandev.can_restart()

    return OPStart


#####################################################################
# Operation BIC-2200 DisCharger Meanwell
def DisCharger_BIC2200_Set(val, force=0):
    try:
        if dev.mwcandev == None:
            mylogs.error("DisCharger_BIC2200_Set mwcandev not exists")
            return

        mylogs.verbose("DisCharger_BIC2200_Set entry - value: " + str(val) + " Force: " + str(force))

        # Check Mode to prevent to set it again if not needed
        # 0=Charger; 1=DisCharger
        status.BICChargeDisChargeMode = dev.mwcandev.BIC_chargemode(0, 0)
        if status.BICChargeDisChargeMode == 0:
            mylogs.verbose("Charger_Device_Set: Try to set BIC2200 to DisCharge Mode")
            if ((val != 0) and (force == 0)) or (status.BatteryEMPTY == 1):  # if shutdown, we dont have to change it to discharge mode
                mylogs.info("StartStopOperationDisCharger: Set BIC2200 to DisCharge Mode")
                dev.mwcandev.BIC_chargemode(1, 1)  # set BIC to DisChargemode
                sleep(0.2)
                status.BICChargeDisChargeMode = dev.mwcandev.BIC_chargemode(0, 0)
                MW_EEPROM_Counter_INC(1, 1)
                mylogs.info("StartStopOperationDisCharger: BIC2200 mode: " + str(status.BICChargeDisChargeMode))

        # read voltage from BIC device
        vout = dev.mwcandev.v_out_read()

        # Calculate current for meanwell + or - to the actual power from PV / Grid
        # *-10000 --> Vout and iout value is *100 --> 2x100 = 10000
        # charging/discharging current in *100 for meanwell --> e.g. 2600 = 26A

        Current = (val * 10000) / vout

        IntCurrent = int(Current)
        OPStart = True  # device start

        if IntCurrent >= cfg.MaxDisChargeCurrent:
            IntCurrent = cfg.MaxDisChargeCurrent

        # calculate ZeroDelta if configured
        ZeroDelta = int((status.ZeroExportWatt / vout) * 10000)
        mylogs.verbose("ZERODELTA IS: " + str(ZeroDelta))

        # BIC device has a minimal DisCharge current
        # Stop if this value is reached or allow take power from grid to charge
        if IntCurrent < cfg.MinDisChargeCurrent:
            if cfg.MW_BIC2200_ForceAlwaysOn == 1:  # BIC set to Min
                IntCurrent = cfg.MinDisChargeCurrent
                mylogs.info(
                    "Meanwell BIC: Current too small - "
                    + str(IntCurrent)
                    + " - MinCurrent: "
                    + str(cfg.MinDisChargeCurrent)
                    + " - ZeroDelta: "
                    + str(ZeroDelta)
                    + " -> Always ON"
                )
                OPStart = True
            else:
                IntCurrent = 0
                mylogs.info(
                    "Meanwell BIC: Current too small - "
                    + str(IntCurrent)
                    + " - MinCurrent: "
                    + str(cfg.MinDisChargeCurrent)
                    + " - ZeroDelta: "
                    + str(ZeroDelta)
                    + " -> Device OFF"
                )
                OPStart = False

        if IntCurrent != status.LastDisChargerSetCurrent:
            if (status.actchargercounter >= cfg.MeterUpdateDisChargeCounter) or (force == 1):
                if (status.LastDisChargerGetCurrent < (status.LastDisChargerSetCurrent - 50)) and (status.BMSSOC < 3):
                    if status.BatteryEMPTY != 1:
                        mylogs.info(
                            "Charger_Device_Set: >>>> NO SET -> BATTERY ALMOST EMPTY: "
                            + str(IntCurrent)
                            + " (Last current GET: "
                            + str(status.LastDisChargerGetCurrent)
                            + " ->  Last current SET: "
                            + str(status.LastDisChargerSetCurrent)
                            + " <<<<"
                        )
                    if (IntCurrent == 0) and (force == 1):
                        OPStart = False  # Stop device
                    else:
                        OPStart = True  # device start or continue
                else:
                    mylogs.info("Meanwell BIC: Set new current to: " + str(IntCurrent) + "  (Last current: " + str(status.LastDisChargerSetCurrent) + ")")
                    c = dev.mwcandev.BIC_discharge_i(1, IntCurrent)
                    status.LastDisChargerSetCurrent = IntCurrent
                    MW_EEPROM_Counter_INC(1)
                    status.actchargercounter = 1  # Reset counter to 1
                    sleep(0.1)  # wait for next read to change BIC
            else:
                mylogs.info("Meanwell BIC: Wait for next change: " + str(status.actchargercounter) + "  of: " + str(cfg.MeterUpdateDisChargeCounter))
                status.actchargercounter += 1

        else:
            mylogs.info("Meanwell BIC: No new DisCharge current to set. Last current: " + str(status.LastDisChargerSetCurrent))

        # try to set the new ChargeCurrent if possible
        if OPStart == True:  # if true start mw device
            mylogs.verbose("OPSTART TRUE : Start BIC2200")
            status.DisChargerStatus = 1
            StartStopOperationDevice(1, 1, force)
        else:
            mylogs.verbose("OPSTART FALSE: Stop BIC2200")
            status.DisChargerStatus = 0
            StartStopOperationDevice(0, 1, force)

        sleep(0.2)
        status.LastDisChargerGetCurrent = dev.mwcandev.i_out_read()
        NewVal = int((status.LastDisChargerGetCurrent * vout) / -10000)

        mylogs.info(
            "Meanwell BIC: W Battery_Vout:"
            + str(vout / 100)
            + ":V: Battery_I_out:"
            + str(status.LastDisChargerGetCurrent / 100)
            + ":A: I Calc:"
            + str(IntCurrent)
            + " = "
            + str(IntCurrent / 100)
            + ":A --> WATT: "
            + str(NewVal)
        )

        status.LastWattValueUsedinDevice = NewVal

    except Exception as e:
        mylogs.error("DisCharger_BIC2200_Set: EXEPTION !")
        mylogs.error(str(e))
        # dev.mwcandev.can0.flush_tx_buffer() #flush buffer to clear message queue
        dev.mwcandev.can_restart()

    return


#####################################################################
#####################################################################
#####################################################################
# Operation Lumentree reopen if Device has communication errors
def Lumentree_ReOpen():
    # mylogs.warning("Lumentree_ReOpen DISABLED !") #perhaps not needed since port is open
    mylogs.warning("Lumentree_ReOpen EXECUTE !")
    status.ltcounter = status.ltcounter + 1
    try:
        dev.LT1.lt232_close()
        if cfg.lt_count > 1:
            dev.LT2.lt232_close()
        if cfg.lt_count > 2:
            dev.LT3.lt232_close()
        sleep(0.2)

        dev.LT1.lt232_open()
        if cfg.lt_count > 1:
            dev.LT2.lt232_open()
        if cfg.lt_count > 2:
            dev.LT3.lt232_open()
        sleep(0.2)

    except Exception as e:
        mylogs.error("LUMENTREE REOPEN FAILED !")
        mylogs.error(str(e))
    return


#####################################################################
# Check periodically if Lumentree is still online. If not try to reopen
def Lumentree_Check():
    if cfg.Selected_Device_DisCharger != 1:
        return

    mylogs.verbose("------> Lumentree Check Alive ...")
    try:
        status.LT1_Temperature = int(dev.LT1.readtemp())  # for temperature test
        if cfg.lt_count > 1:
            status.LT2_Temperature = int(dev.LT2.readtemp())  # for temperature test
        if cfg.lt_count > 2:
            status.LT3_Temperature = int(dev.LT3.readtemp())  # for temperature test
        # sleep(0.1)
        mylogs.debug("------> Lumentree Check Alive OK. BattVoltage: " + str(status.DisChargerVoltage))
        return 1

    except Exception as e:
        mylogs.error("------> LUMENTREE CHECK ALIVE EXEPTION !")
        mylogs.error(str(e))
        status.LastWattValueUsedinDevice = 10  #
        status.DisChargerStatus = 1  # try again every time a new Power value is received
        return 0


#####################################################################
# Operation Lumentree Sun600/1000/2000
def DisCharger_Lumentree_Set(val, force=0):
    LToutput = 0
    mylogs.verbose("DisCharger_Lumentree_Set entry - value: " + str(val))

    if cfg.MaxDisChargeWATT <= val:
        outpower = cfg.MaxDisChargeWATT
    else:
        if cfg.MinDisChargeWATT >= val:
            outpower = 0  # Stop DisCharger, too low Watt needed
        else:
            outpower = val

    if val == 0:
        outpower = 0

    if force == 0:
        if (status.LastWattValueUsedinDevice == 0) and (status.DisChargerStatus == 1):
            # Lumentree has not raised the output, but we get 0 already to set off again
            p = 10
        else:
            p = abs(status.LastWattValueUsedinDevice - outpower)

        if p <= 8:  # since Lumentree don't have exact value we can set, use +/-8 to test if we have the same value
            mylogs.verbose("DisCharger_Lumentree_Set: No change to DISCharger output: " + str(status.LastWattValueUsedinDevice) + " NewWatt Value: " + str(outpower))
            return 0  # no need to set the same again, mainly for max power, delta is handled above
        else:
            mylogs.verbose("DisCharger_Lumentree_Set: LastWATT value: " + str(status.LastWattValueUsedinDevice) + " NewWatt Value: " + str(outpower))

        # only needs to read one LT for DC voltage, all should be connected to the same battery
        try:
            DCvoltage = 100  # for force to goto set watt output if LT reconnect
            DCvoltage = dev.LT1.readDCvoltage()
            sleep(0.05)
        except Exception as e:
            mylogs.error("LUMENTREE SET EXEPTION READ DC VOLTAGE!")
            mylogs.error(str(e))

        if DCvoltage < 10:
            if status.DisChargerStatus == 0:
                # only if DisCarger is set already to OFF, otherwise proceed to power off
                mylogs.info("DisCharger_Lumentree_Set: DC volatge too low. Probably Battery empty or defect : " + str(DCvoltage))
                return
            else:
                # Disable DisCharger
                outpower = 0

    #    sleep(0.1)  #wait 0.1 seconds to read next value

    # calculate the power for each Lumentree

    if outpower <= cfg.lt1_maxwatt:
        outpower1 = outpower
    else:
        outpower1 = cfg.lt1_maxwatt
    outpower = outpower - outpower1

    if outpower <= cfg.lt2_maxwatt:
        outpower2 = outpower
    else:
        outpower2 = cfg.lt2_maxwatt
    outpower = outpower - outpower2

    if outpower <= cfg.lt3_maxwatt:
        outpower3 = outpower
    else:
        outpower3 = cfg.lt3_maxwatt
    outpower = outpower - outpower3

    mylogs.info("DisCharger_Lumentree_Set : Outpower set to LT1: " + str(outpower1) + "   LT2: " + str(outpower2) + "   LT3: " + str(outpower3))
    if outpower != 0:
        mylogs.info("DisCharger_Lumentree_Set : Outpower should be 0 now - check settings ! - " + str(outpower))

    try:
        # Lumentree Inverter 1
        mylogs.verbose("DisCharger_Lumentree_Set   (1) : " + str(outpower1))
        dev.LT1.set_watt_out(int(outpower1))

        # Lumentree Inverter 2
        if cfg.lt_count > 1:
            mylogs.verbose("DisCharger_Lumentree_Set   (2) : " + str(outpower2))
            dev.LT2.set_watt_out(int(outpower2))

        # Lumentree Inverter 3
        if cfg.lt_count > 2:
            mylogs.verbose("DisCharger_Lumentree_Set   (3) : " + str(outpower3))
            dev.LT3.set_watt_out(int(outpower3))

        # read Watt out, do it after all, to prevent multible sleeps
        # Lumentree Inverter 1
        sleep(0.2)  # wait 0.2 seconds to read value
        LToutput = dev.LT1.read_watt_out()
        # Lumentree Inverter 2
        if cfg.lt_count > 1:
            LToutput = LToutput + dev.LT2.read_watt_out()
        # Lumentree Inverter 3
        if cfg.lt_count > 2:
            LToutput = LToutput + dev.LT3.read_watt_out()

        # Lumentree return sometime > 1 if set to zero
        # if(status.LastWattValueUsedinDevice <= 3): status.LastWattValueUsedinDevice = 0

        # This must be set lastest possible to check Status in other functions
        # Since Lumentree needs some time to set the output, wait until LT1.read_watt_out really is 0.
        if (val == 0) and (LToutput == 0):
            status.DisChargerStatus = 0
        else:
            status.DisChargerStatus = 1

        status.LastWattValueUsedinDevice = LToutput

    except Exception as e:
        mylogs.error("LUMENTREE SET EXEPTION !")
        mylogs.error(str(e))
        status.LastWattValueUsedinDevice = 10  # force to go here
        status.DisChargerStatus = 1  # prevent not setting off, if LT is back again
        Lumentree_ReOpen()
        if (force == 1) and (val == 0):  # be really sure that LT is set to 0 on exit
            dev.LT1.set_watt_out(0)
            if cfg.lt_count > 1:
                dev.LT2.set_watt_out(0)
            if cfg.lt_count > 2:
                dev.LT3.set_watt_out(0)

    mylogs.info("DisCharger_Lumentree_Set read Total: " + str(status.LastWattValueUsedinDevice))
    return


#####################################################################
# Operation Soyo 1000/1200
def DisCharger_Soyo_Set(val, force=0):
    mylogs.verbose("DisCharger_Soyo_Set entry - value: " + str(val))

    if cfg.MaxDisChargeWATT <= val:
        outpower = cfg.MaxDisChargeWATT
    else:
        if cfg.MinDisChargeWATT >= val:
            outpower = 0  # Stop DisCharger, too low Watt needed
        else:
            outpower = val

    if val == 0:
        outpower = 0

    if force == 0:
        p = abs(status.LastWattValueUsedinDevice - outpower)

        if p <= 8:  # since Lumentree don't have exact value we can set, use +/-8 to test if we have the same value
            mylogs.verbose("DisCharger_Soyo_Set: No change to DISCharger output: " + str(status.LastWattValueUsedinDevice) + " NewWatt Value: " + str(outpower))
            return 0  # no need to set the same again, mainly for max power, delta is handled above
        else:
            mylogs.verbose("DisCharger_Soyo_Set: LastWATT value: " + str(status.LastWattValueUsedinDevice) + " NewWatt Value: " + str(outpower))

    if outpower <= cfg.soyo_maxwatt:
        outpower = outpower
    else:
        outpower = cfg.soyo_maxwatt

    try:
        mylogs.verbose("DisCharger_Soyo_Set   (1) : " + str(outpower))
        dev.soyo.set_watt_out(int(outpower))
        sleep(0.2)  # wait 0.2 seconds to write next value

        # This must be set lastest possible to check Status in other functions
        # Since Lumentree needs some time to set the output, wait until LT1.read_watt_out really is 0.
        if (val == 0) and (outpower == 0):
            status.DisChargerStatus = 0
        else:
            status.DisChargerStatus = 1

        status.LastWattValueUsedinDevice = outpower

    except Exception as e:
        mylogs.error("SOYO SET EXEPTION !")
        mylogs.error(str(e))
        status.LastWattValueUsedinDevice = 10  # force to go here
        status.DisChargerStatus = 1  # prevent not setting off, if LT is back again
        Lumentree_ReOpen()
        if (force == 1) and (val == 0):  # be really sure that LT is set to 0 on exit
            dev.soyo.set_watt_out(0)

    mylogs.info("DisCharger_Soyo_Set read Total: " + str(status.LastWattValueUsedinDevice))
    return


def GetChargerVoltage():
    mylogs.debug("GetChargerVoltage ...")
    try:
        if cfg.Selected_Device_Charger <= 1:  # BIC and NPB-abc0
            status.ChargerVoltage = dev.mwcandev.v_out_read()

        if cfg.Selected_Device_Charger == 10:  # mPSU
            status.ChargerVoltage = dev.mPSU.voltage_read(cfg.mPSU1_nodeid)

    except Exception as e:
        if dev.mwcandev != None:
            # dev.mwcandev.can0.flush_tx_buffer() #flush buffer to clear message queue
            dev.mwcandev.can_restart()

        mylogs.error("GetChargerVoltage EXEPTION !")
        mylogs.error(str(e))
    return status.ChargerVoltage


def GetDisChargerVoltage():
    mylogs.debug("GetDisChargerVoltage ...")
    try:
        if cfg.Selected_Device_DisCharger == 0:  # BIC2200
            status.DisChargerVoltage = dev.mwcandev.v_out_read()

        if cfg.Selected_Device_DisCharger == 1:  # Lumentree
            status.DisChargerVoltage = dev.LT1.readDCvoltage() * 10  # return 3 digits, need 4 for compare --> *10
            sleep(0.05)
            mylogs.debug("GetDisChargerVoltage: Nothing to do here, this is already done in Lumentree_Check !")

    except Exception as e:
        if dev.mwcandev != None:
            # dev.mwcandev.can0.flush_tx_buffer() #flush buffer to clear message queue
            dev.mwcandev.can_restart()

        mylogs.error("GetDisChargerVoltage EXEPTION !")
        mylogs.error(str(e))
    return status.ChargerVoltage


def GetBatteryVoltage():
    mylogs.debug("GetBatteryVoltage ...")
    try:
        if cfg.BatteryVoltageSource == 0:
            status.BatteryVoltage = cfg.FixedChargeVoltage  # do not use it, assume always full

        if cfg.BatteryVoltageSource == 1:
            status.BatteryVoltage = status.BMSVoltage

        if cfg.BatteryVoltageSource == 2:
            GetChargerVoltage()
            status.BatteryVoltage = status.ChargerVoltage

        if cfg.BatteryVoltageSource == 3:
            GetDisChargerVoltage()
            status.BatteryVoltage = status.DisChargerVoltage

        # add the voltage correction to the value + or -
        status.BatteryVoltage = status.BatteryVoltage + cfg.BatteryVoltageCorrection

    except Exception as e:
        mylogs.error("GetBatteryVoltage EXEPTION !")
        mylogs.error(str(e))

    return


def CheckTemperatures():
    mylogs.debug("CheckTemps ...")
    try:
        if cfg.Selected_Device_Charger == 0:
            status.MW_BIC_Temperature = round(int(dev.mwcandev.temp_read()) / 10)  # need only 2 digits
            if status.MW_BIC_Temperature > cfg.MW_BIC2200_MaxTemp:
                mylogs.error("CheckTemperatures: MW_BIC_Temperature Temperature too high")

        if cfg.Selected_Device_Charger == 1:
            status.MW_NPB_Temperature = round(int(dev.mwcandev.temp_read()) / 10)  # need only 2 digits
            if status.MW_NPB_Temperature > cfg.MW_NPB_MaxTemp:
                mylogs.error("CheckTemperatures: MW_NPB_Temperature Temperature too high")

        if cfg.Selected_Device_Charger == 10:
            status.mPSU_Temperature = round(int(dev.mPSU.readtemp(cfg.mPSU1_nodeid)) / 10)  # need only 2 digits
            if status.mPSU_Temperature > 60:  # cfg.mPSU_MaxTemp):
                mylogs.error("CheckTemperatures: mPSU_Temperature Temperature too high")

        if cfg.Selected_Device_DisCharger == 1:
            if status.LT1_Temperature > cfg.lt_MaxTemp:
                mylogs.error("CheckTemperatures: LT1 Temperature too high: " + str(status.LT1_Temperature))
            if status.LT2_Temperature > cfg.lt_MaxTemp:
                mylogs.error("CheckTemperatures: LT2 Temperature too high: " + str(status.LT2_Temperature))
            if status.LT3_Temperature > cfg.lt_MaxTemp:
                mylogs.error("CheckTemperatures: LT3 Temperature too high: " + str(status.LT3_Temperature))

        if cfg.Selected_BMS > 0:
            if BMSstatus.BMSTemp_Mosfet > cfg.BMS_MaxTempMosFet:
                mylogs.error("CheckTemperatures: BMSTemp_Mosfet Temperature too high")
            if BMSstatus.BMSTemp1 > cfg.BMS_MaxTemp1:
                mylogs.error("CheckTemperatures: BMSTemp1 Temperature too high")
            if BMSstatus.BMSTemp2 > cfg.BMS_MaxTemp2:
                mylogs.error("CheckTemperatures: BMSTemp2 Temperature too high")

        mylogs.info(
            "CheckTemperatures: MWBIC: "
            + str(status.MW_BIC_Temperature)
            + " MWNPB: "
            + str(status.MW_NPB_Temperature)
            + " LT1: "
            + str(status.LT1_Temperature)
            + " LT2: "
            + str(status.LT2_Temperature)
            + " LT3: "
            + str(status.LT3_Temperature)
            + " BMSFET: "
            + str(BMSstatus.BMSTemp_Mosfet)
            + " BMST1: "
            + str(BMSstatus.BMSTemp1)
            + " BMST2: "
            + str(BMSstatus.BMSTemp2)
        )

    except Exception as e:
        mylogs.error("CheckTemperatures EXEPTION !")
        mylogs.error(str(e))

    return


def CalcBatteryWh():
    mylogs.debug("CalcBatteryWh ...")
    try:
        if status.LastWattValueUsedinDevice <= 0:
            EF = 1  # Charger do not need a correction, we read the output of the charger
        else:
            EF = status.DisCharger_efficacy_factor

        now = datetime.datetime.now()
        diff = (now - status.LastEstWhTime).total_seconds()
        # get the millWattHour in seconds of the LastWattValueUsedinDevice
        # -1000: we get negative value for charging, convert to positive values
        # DisCharger_efficacy_factor needed because we need more current than we request WATT of the DisCharger
        LastWatt_mWh = (status.LastWattValueUsedinDevice + status.ext_lastwattusedindevice) * EF * -1000 / 3600

        # and multiply with the duration
        Bat_mWh = LastWatt_mWh * diff
        status.EstBatteryWh = status.EstBatteryWh + Bat_mWh
        status.LastEstWhTime = now
        mylogs.verbose(
            "CalcBatteryWh: LastWatt_mWh :"
            + str(round(LastWatt_mWh, 2))
            + " - Bat_mAH: "
            + str(round(Bat_mWh, 2))
            + " - EF: "
            + str(round(EF, 2))
            + " - TimeDiff: "
            + str(round(diff, 2))
        )

    except Exception as e:
        mylogs.error("CalcBatteryWh EXEPTION !")
        mylogs.error(str(e))


#####################################################################
# calculate the output power by array
#####################################################################
def SetPowerValArray(CDlength, val):
    try:
        if CDlength == status.powercalccount:
            return

        mylogs.info(">>>> SetPowerValArray <<<< CurrentLength: " + str(status.powercalccount) + "  NewLength: " + str(CDlength) + " Value: " + str(val))
        for x in range(len(powervalarray)):
            powervalarray[x] = val
        status.powercalccount = CDlength  # save the length

        """
        if(CDlength < status.powercalccount):
            status.powercalccount = CDlength #save the length


        #New length is greater than old one, just fill the array with the current value
        if(CDlength > status.powercalccount):
            for x in range(max(1,status.powercalccount)): 
                powervalarray[x] = Val
            status.powercalccount = CDlength #save the length
        """

    except Exception as e:
        mylogs.error("SetPowerValArray EXEPTION !")
        mylogs.error(str(e))

    return


def getoutputpower(val):
    mylogs.verbose("getoutputpower entry value " + str(val))

    try:
        if (datetime.datetime.now() - status.CheckDeviceTime).total_seconds() > 15:  # check every 30 seconds
            mylogs.debug("getoutputpower: CHECK DEVICES")
            status.WebRebootSDcounter = 0  # reset rebootcounter for webinterface
            status.CheckDeviceTime = datetime.datetime.now()
            Lumentree_Check()  # Check every minute if LT is online, and get CD Voltage, if not try to reconnect
            GetBMSData()  # Read all data and set some status IDs
            GetBatteryVoltage()
            CheckTemperatures()

        # check the total Watt,
        status.CurrentWattValue = val
        status.CurrentTotalWatt = status.CurrentWattValue + status.LastWattValueUsedinDevice

        mylogs.debug("getoutputpower: CurrentTotalWatt         : " + str(status.CurrentTotalWatt))
        mylogs.debug("getoutputpower: LastWattValueusedinDevice: " + str(status.LastWattValueUsedinDevice))
        # add new value to array
        status.LastPowerArrayPosition += 1
        if status.LastPowerArrayPosition >= status.powercalccount:
            status.LastPowerArrayPosition = 0
        powervalarray[status.LastPowerArrayPosition] = status.CurrentTotalWatt
        # get average value of array
        r = round(sum(powervalarray[0 : status.powercalccount]) / status.powercalccount)
        mylogs.verbose("getoutputpower: Array Length: " + str(status.powercalccount) + " Array: " + str(powervalarray))

        status.CurrentAverageWatt = r

        mqttpublish()
        printlcd()
        logstatus()
        CalcBatteryWh()

    except Exception as e:
        mylogs.error("GETOUTPUTPOWER EXEPTION !")
        mylogs.error(str(e))

    return r


#####################################################################
# Setup Charge / Discharge here depending of Power
# power negative = from PV ; power positive = from Grid
def process_power(power):
    try:
        mylogs.verbose("--------------- NEW VALUE TO PROCESS --------------- ")
        mylogs.verbose("process_power entry: " + str(power))
        if status.ProcessActive == 1:
            mylogs.info(">>>>>>>>>> process_power process still active, skip this round <<<<<<<<<<")
            return

        if cfg.MeterSwapValue == 1:
            # Value is in the wrong +/- order, swap it
            power = power * (-1)
            mylogs.debug("process_power swap: " + str(power))

        now = datetime.datetime.now()
        diff = (now - status.LastEstWhTime).total_seconds()
        diffrun = (status.LastEndRunTime - status.LastStartRunTime).total_seconds()
        diffmeter = (now - status.LastStartRunTime).total_seconds()
        if diffrun > status.MaxRunTime:
            status.MaxRunTime = diffrun

        if cfg.ShowRuntime == 1:
            mylogs.info("-> Last Run Duration: " + str(diffrun) + " - MaxRunTime: " + str(status.MaxRunTime) + " - Lastmetertime: " + str(diffmeter))

        if diffmeter < (cfg.MeterDelaytime - 0.1):  # allow 100ms diffrence
            mylogs.warning("process_power: Too fast power meter reading ! Ignore value: " + str(diffmeter))
            return

        status.ProcessActive = 1

        # Start new Process
        status.LastStartRunTime = now

        NewPower = getoutputpower(power)

        mylogs.verbose("TotalWatt: " + str(power) + "W  -  CalcAverage: " + str(status.CurrentAverageWatt) + "W")

        #######################################################################################################################################
        #######  Method 0 DEBUG ###############################################################################################################
        #######################################################################################################################################
        if cfg.PowerControlmethod == 0:
            mylogs.error("PowerControlmethod: 0 - DO NOT USE - ONLY FOR DEBUG")

        #######################################################################################################################################
        #######  Method 1 Universal, Just check if positive or negative power #################################################################
        #######################################################################################################################################
        if cfg.PowerControlmethod == 1:
            mylogs.debug("PowerControlmethod: 1 - Universal mode")

            """
            if (status.ZeroImportWatt > 0):      #charger aviod to take from Grid for charging, check if still valid
                if((NewPower + status.ZeroImportWatt) > cfg.ZeroDeltaChargerWATT):
                    status.ZeroImportWatt = 0   #too much delta, reset and use normal way
                else:
                    mylogs.verbose("ChargeMethod: 1 with ZeroImport")
                    StartStopOperationCharger(NewPower)
                    return power
            """
            # Charge / Discharge calculation
            # charge, getting power from PV, charge battery now
            if NewPower < 0:
                mylogs.debug("ChargeMethod: 1")
                StartStopOperationDisCharger(0)  # stop Discharging
                StartStopOperationCharger(NewPower)
            else:
                # discharge, getting power from Battery to house
                # if (NewPower >= 0):
                mylogs.debug("DisChargeMethod: 1")
                StartStopOperationCharger(0)  # stop charging
                StartStopOperationDisCharger(NewPower)
        # END ControlMethod 1

        #######################################################################################################################################
        # Method 2...
        #######################################################################################################################################
        #       if (cfg.PowerControlmethod == 2):
        #            print("Method 2")
        #       END ControlMethod 2

        #######################################################################################################################################
        #######  Method 255 Simulator #########################################################################################################
        #######################################################################################################################################
        if cfg.PowerControlmethod == 255:
            mylogs.debug("PowerControlmethod 255 - Simulator")
            if power > 0:
                StartStopOperationCharger(0)
                StartStopOperationDisCharger(NewPower)
            else:
                StartStopOperationCharger(NewPower)
                StartStopOperationDisCharger(0)
        # END ControlMethod 255

    except Exception as e:
        mylogs.error("process_power EXEPTION !")
        mylogs.error(str(e))
        status.ProcessActive = 0

    status.LastEndRunTime = datetime.datetime.now()
    status.ProcessActive = 0
    return  # as fallback


#######################################################################################################################################
#######################################################################################################################################
#######################################################################################################################################
#######  Get Power function ###########################################################################################################
#######################################################################################################################################


#####################################################################
# http request
def http_request():
    # --------- Read Power Meter via http
    try:
        power = METER.GetPowermeterWatts()
        mylogs.verbose("http: Power message: " + str(power))

    except Exception as e:
        mylogs.error("HTTP CONNECTION ERROR")
        mylogs.error(str(e))
        # reset Empty and Full, to be sure so start at 0 after a disconnect
        status.BatteryEMPTY = 0
        status.BatteryFULL = 0

        # Stop Operation if setting set
        if cfg.MeterStopOnConnectionLost == 1:
            StartStopOperationCharger(0, 1)
            StartStopOperationDisCharger(0, 1)
        return

    process_power(power)
    return


#####################################################################
# Simulator request, just a random number
def simulator_request():
    # --------- Create a random power value

    power = random.randrange(-500, 500, 10)
    power = -50 - status.LastWattValueUsedinDevice
    process_power(power)


#####################################################################
#####################################################################
# mqtt functions
# def mqtt_on_connect(client, userdata, flags, rc): #mqtt < 2.00
def mqtt_on_connect(client, userdata, flags, reason_code, properties):
    mylogs.info("mqtt: Connected with mqttserver")
    # reset Empty and Full, to be sure so start at 0 after a disconnect
    status.BatteryEMPTY = 0
    status.BatteryFULL = 0
    # Subscribe for actual Power from mqtt server
    if cfg.GetPowerOption == 0:
        mylogs.info("mqtt: Subscribe for toipc " + cfg.mqttsubscribe)
        dev.mqttclient.subscribe(cfg.mqttsubscribe, qos=2)
    return


# def mqtt_on_disconnect(client, userdata, rc): #mqtt <2.00
def mqtt_on_disconnect(client, userdata, flags, reason_code, properties):
    mylogs.warning("mqtt: DISConnected from mqttserver")
    mylogs.warning("mqtt: " + str(client))
    #    if rc != 0:
    if reason_code != 0:
        mylogs.error("mqtt: Unexpected disconnect with mqttserver. Result: " + str(reason_code))
        if cfg.MeterStopOnConnectionLost == 1:
            mylogs.error("mqtt: LOST CONNECTION -> STOP ALL DEVICES")
            StartStopOperationCharger(0, 1)
            StartStopOperationDisCharger(0, 1)
    return


def mqtt_on_message(client, userdata, message):
    power = str(message.payload.decode("utf-8"))
    mylogs.debug("mqtt: Power message: " + power)
    # print("message received ", val)
    # print("message topic=",message.topic)
    # print("message qos=",message.qos)
    # print("message retain flag=",message.retain)
    process_power(round(int(power)))
    # mylogs.info("mqtt: Power message END")
    return


# Mqtt < 2.00
# def mqtt_on_subscribe(client, userdata, mid, granted_qos):
#    mylogs.info("mqtt: Qos granted: " + str(granted_qos))
#    return


def mqtt_on_subscribe(client, userdata, mid, reason_codes, properties):
    for sub_result in reason_codes:
        if sub_result < 128:
            mylogs.info("mqtt: Qos granted: " + str(sub_result))
            return
        else:
            mylogs.info("mqtt: Something went wrong during subscribe: " + str(sub_result))
            return


# add logger verbose
def verbose(self, message, *args, **kwargs):
    if self.isEnabledFor(logging.VERBOSE):
        self._log(logging.VERBOSE, message, args, **kwargs)


#######################################################################################################################################
#######################################################################################################################################
#                  *** Main ***                         ###############################################################################
#######################################################################################################################################

#################################################################
# Register exit functions
atexit.register(on_exit)
signal.signal(signal.SIGHUP, handle_exit)  # 1
signal.signal(signal.SIGINT, handle_exit)  # 2 Interrupt from keyboard CRTL-C mostly
signal.signal(signal.SIGQUIT, handle_exit)  # 3
signal.signal(signal.SIGTERM, handle_exit)  # 15

print("")
print("#####################################################")
print("      _       ______      ______  ______           ")
print("     / \     |_   _ \   .' ___  ||_   _ `.         ")
print("    / _ \      | |_) | / .'   \_|  | | `. \ .--.   ")
print("   / ___ \     |  __'. | |         | |  | |( (`\]  ")
print(" _/ /   \ \_  _| |__) |\ `.___.'\ _| |_.' / `'.'.  ")
print("|____| |____||_______/  `.____ .'|______.' [\__) ) ")
print("#####################################################")
print("")
print("######################################################")
print("# THERE IS NO GURANTEE FOR AN ERROR FREE EXECUTION   #")
print("# YOU TAKE THE TOTAL RISK IF YOU USE THIS SCRIPT !!! #")
print("# ONLY FOR USE WITH LIFEPO4 CELLS !!!                #")
print("# BATTERIES CAN BE DANGEROUS !!!                     #")
print("# BE SURE YOU KNOW WHAT YOU ARE DOING !!             #")
print("# THE AUTHOR(S) IS NOT LIABLE FOR ANY DAMAGE !!      #")
print("# YOU HAVE BEEN WARNED !                             #")
print("######################################################")
print("")

#################################################################
# Init global variables
status = Devicestatus()

#################################################################
# Get global cfg from file

# Define a custom logging method for the new level
logging.VERBOSE = 15
logging.addLevelName(logging.VERBOSE, "VERBOSE")
logging.Logger.verbose = verbose

# Create a new logger mylogs
mylogs = logging.getLogger()

# Ckeck if we should wait x seconds before start (Network interface up)
if len(sys.argv) == 2:
    try:
        mylogs.info("Wait some time ... \n")
        s = int(sys.argv[1])
        sleep(s)
    except Exception as e:
        mylogs.error("ERROR IN SLEEP PARAMETER !\n")
        mylogs.error(str(e))

# Read conf file
spath = os.path.dirname(os.path.realpath(sys.argv[0]))
status.configfile = spath + "/BSsetup.conf"
cfg = chargerconfig()

# put it into status class for easier status info for webserver
# needs to be here because it will overwrite the value with 0 during exit
status.EstBatteryWh = cfg.EstBatteryWh

if cfg.i_changed_my_config == 0:
    print("PLEASE SET UP YOUR DEVICE IN BSsetup.conf !!")
    print("CHECK ALL PARAMETERS CAREFULLY !!!")
    print("BY SETTING TO 1 YOU ACCEPT THE USING THIS SCRIPT AT YOUR OWN RISK")
    sys.exit()

# Init all needed DevVariables with None
bs_ext = None
dev = DEV()

#################################################################
# Check Basic Paramter if they look ok
if CheckPatameter() == 1:
    print("Someting wrong with yout paramaters - Check all settings")
    mylogs.error("\n\nSometing wrong with yout paramaters - Check all settings!\n")
    sys.exit(1)

#################################################################
#################################################################
# init average power calculation array
powervalarray = []
for x in range(max(1, max(cfg.ChargerPowerCalcCount, cfg.DisChargerPowerCalcCount))):
    powervalarray.append(x)
status.powercalccount = max(cfg.ChargerPowerCalcCount, cfg.DisChargerPowerCalcCount)

bs_ext = BatteryScript_external(cfg.loglevel)

#################################################################
#################################################################
############  L C D - S E C T I O N  ############################
############ INIT 1st to display info ###########################
#################################################################
# LCD/OLED INIT
if cfg.Selected_LCD != 0:
    mylogs.info("Init display")
    if cfg.Selected_LCD == 1:
        try:
            dev.display = i2clcd(cfg.lcdi2cadr)
            dev.display.lcd_clear()
        except Exception as e:
            mylogs.error("\n\nEXECETION INIT DISPLAY !\n")
            mylogs.error(str(e))
            sys.exit(1)

#################################################################
#################################################################
############  C H A R G E R - S E C T I O N  ####################
#################################################################
#################################################################
# CAN INIT for CAN device: 0=bic2200, 1=NPB
if cfg.Selected_Device_Charger <= 1:
    mylogs.verbose("OPEN CAN DEVICE: MEANWELL")

    # Init and get get Type of device
    try:
        dev.mwcandev = mwcan(cfg.Selected_Device_Charger, cfg.MW_USEDID, "", cfg.loglevel)
        mwt = dev.mwcandev.can_up()
        mylogs.info(mwt)

    except Exception as e:
        dev.mwcandev.can_down()  # Exception -> close the bus
        dev.mwcandev = None
        mylogs.error("\n\nEXCEPTION Meanwell Device not found !\n")
        mylogs.error(str(e))
        printlcd("Exception open CAN-device for Meanwell", str(e))
        sys.exit(1)

    # first stop the device directly after startup check the paramaters
    mylogs.info("Meanwell Operation STOP at startup")

    # First Stop the device to have a defind state
    StartStopOperationDevice(0, 1, 1)

    mylogs.debug(mwt + " Serial     : " + dev.mwcandev.serial_read())
    mylogs.debug(mwt + " Firmware   : " + str(dev.mwcandev.firmware_read()))
    mylogs.info(mwt + " temperature: " + str(dev.mwcandev.temp_read() / 10) + " C")

    # Set ChargerMainVoltage of the charger to check the parameters, needs to be in value *100, 24 = 2400
    status.ChargerMainVoltage = dev.mwcandev.dev_Voltage * 100

    # get grid voltage from meanwell device
    Voltage_IN = 0
    Voltage_IN = round(float(dev.mwcandev.v_in_read() / 10))
    Voltage_IN = Voltage_IN + cfg.Voltage_ACIN_correction
    mylogs.info("Grid Voltage: " + str(Voltage_IN) + " V")

    # Meanwell BIC-2200 specific
    if cfg.Selected_Device_Charger == 0:
        # setup Bic2200
        MW_ChargeVoltCorr = cfg.MW_BIC_ChargeVoltCorr

        # set to charge mode first
        sc = dev.mwcandev.system_config(0, 0)
        bic = dev.mwcandev.BIC_bidirectional_config(0, 0)
        mylogs.debug("BIC SystemConfig: " + str(sc) + " BiDirectionalConfig: " + str(bic))
        if (not is_bit(sc, SYSTEM_CONFIG_CAN_CTRL)) or (not is_bit(bic, 0)):
            print("MEANWELL BIC2200 IS NOT IN CAN CONTROL MODE OR BI DIRECTIONAL MODE OR NOT OFF DURING STARTUP WHICH IS NEEDED !!!\n")
            c = input("SET CONTROLS NOW ? (y/n): ")
            if c == "y":
                sc = dev.mwcandev.system_config(1, 1)
                bic = dev.mwcandev.BIC_bidirectional_config(1, set_bit(bic, 0))
                print("YOU HAVE TO POWER CYCLE OFF/ON THE MEANWELL BIC2200 NOW BY YOURSELF !!")
                MW_EEPROM_Counter_INC(0, 1)
                MW_EEPROM_Counter_INC(0, 1)
            sys.exit(1)

        # Because the initialisation of Meanwell BIC-2200 is at Charger section
        # the init of BICDISCharger is already there
        # here we check the DisCharge settings
        #    if (cfg.Selected_Device_DisCharger == 0):
        status.DisCharger_efficacy_factor = cfg.MW_BIC2200_efficacy_factor
        # set Min Discharge voltage
        rval = dev.mwcandev.BIC_discharge_v(0, 0)
        if rval != cfg.StopDischargeVoltage + cfg.MW_BIC_DisChargeVoltCorr:
            dev.mwcandev.BIC_discharge_v(1, cfg.StopDischargeVoltage + cfg.MW_BIC_DisChargeVoltCorr)
            MW_EEPROM_Counter_INC(1)
            mylogs.info("SET DISCHARGE VOLTAGE: " + str(rval))
        else:
            mylogs.info("DISCHARGE VOLTAGE ALREADY SET: " + str(rval))

        if cfg.MaxDisChargeCurrent > dev.mwcandev.dev_MaxDisChargeCurrent:
            mylogs.warning("Config max Discharge current is too high ! " + str(cfg.MaxDisChargeCurrent))
            mylogs.warning("Use max charge current from device ! " + str(dev.mwcandev.dev_MaxDisChargeCurrent))
            cfg.MaxDisChargeCurrent = dev.mwcandev.dev_MaxDisChargeCurrent

        if cfg.MinDisChargeCurrent < dev.mwcandev.dev_MinDisChargeCurrent:
            mylogs.warning("Config min discharge current is too low ! " + str(cfg.MinDisChargeCurrent))
            mylogs.warning("Use min discharge current from device ! " + str(dev.mwcandev.dev_MinDisChargeCurrent))
            cfg.MinDisChargeCurrent = dev.mwcandev.dev_MinDisChargeCurrent

        # Read the current mode from BIC-2200
        status.BICChargeDisChargeMode = dev.mwcandev.BIC_chargemode(0, 0)

    #######################
    # Meanwell NBP specific
    if cfg.Selected_Device_Charger == 1:
        # setup NPB
        MW_ChargeVoltCorr = cfg.MW_NPB_ChargeVoltCorr
        sc = dev.mwcandev.system_config(0, 0)
        cuve = dev.mwcandev.NPB_curve_config(0, 0)  # Bit 7 should be 0
        mylogs.debug("NPB SystemConfig: " + str(sc) + " CURVE_CONFIG: " + str(cuve))

        # Bit 7 is 1 --> Charger Mode             #check OFF during startup
        if (is_bit(cuve, CURVE_CONFIG_CUVE)) or ((sc & 0b0000000000000110) != 0):
            print("MEANWELL NPB IS NOT IN PSU MODE / NOT OFF during STARTUP OR EEPROM WRITE IS ENABLED!!!\n")
            c = input("SET PSU MODE NOW ? (y/n): ")
            if c == "y":
                cuve = dev.mwcandev.NPB_curve_config_pos(1, CURVE_CONFIG_CUVE, 0)  # Bit 7 should be 0
                sc = clear_bit(sc, 1)
                sc = clear_bit(sc, 2)
                sc = dev.mwcandev.system_config(1, sc)  # bit 10 only set to 1
                print("YOU HAVE TO POWER CYCLE OFF/ON THE MEANWELL NPB NOW BY YOURSELF !!")
                MW_EEPROM_Counter_INC(0, 1)
            sys.exit(1)

    # Set fixed charge voltage to device BIC and NPB
    rval = dev.mwcandev.v_out_set(0, 0)
    status.MW_ChargeVoltage = cfg.FixedChargeVoltage + MW_ChargeVoltCorr
    if rval != status.MW_ChargeVoltage:
        rval = dev.mwcandev.v_out_set(1, status.MW_ChargeVoltage)
        MW_EEPROM_Counter_INC(0)
        mylogs.info("SET CHARGE VOLTAGE: " + str(rval))
    else:
        mylogs.info("CHARGE VOLTAGE ALREADY SET: " + str(rval))

    # NPB and BIC
    if cfg.MaxChargeCurrent > dev.mwcandev.dev_MaxChargeCurrent:
        mylogs.warning("Config max charge current is too high ! " + str(cfg.MaxChargeCurrent))
        mylogs.warning("Use max charge current from device ! " + str(dev.mwcandev.dev_MaxChargeCurrent))
        cfg.MaxChargeCurrent = dev.mwcandev.dev_MaxChargeCurrent

    if cfg.MinChargeCurrent < dev.mwcandev.dev_MinChargeCurrent:
        mylogs.warning("Config min charge current is too low ! " + str(cfg.MinChargeCurrent))
        mylogs.warning("Use min charge current from device ! " + str(dev.mwcandev.dev_MinChargeCurrent))
        cfg.MinChargeCurrent = dev.mwcandev.dev_MinChargeCurrent

    # start BIC2200 imidiatelly if MW_BIC2200_ForceAlwaysOn is set.
    if cfg.MW_BIC2200_ForceAlwaysOn == 1:
        mylogs.info("Meanwell BIC-2200 AlwaysOn set")
        # Set output to 0 to be sure that the BIC does not start in a high value
        rval = dev.mwcandev.i_out_set(0, 0)
        if rval != dev.mwcandev.dev_MinChargeCurrent:
            mylogs.info("Meanwell BIC-2200 Set MinChargeCurrent")
            dev.mwcandev.i_out_set(1, dev.mwcandev.dev_MinChargeCurrent)
            MW_EEPROM_Counter_INC(0)
        rval = dev.mwcandev.BIC_discharge_i(0, 0)
        if rval != dev.mwcandev.dev_MinDisChargeCurrent:
            mylogs.info("Meanwell BIC-2200 Set MinDisChargeCurrent")
            dev.mwcandev.BIC_discharge_i(1, dev.mwcandev.dev_MinDisChargeCurrent)
            MW_EEPROM_Counter_INC(1)
        status.ChargerStatus = 1
        status.DisChargerStatus = 1
        StartStopOperationDevice(1, 1, 1)

    #######################
    # Check EEPROM write disable (only available with a FW > 02/2024!)
    # Do this at the end of init to write the correct setting to the device before disable EEPROM write
    sc = dev.mwcandev.system_config(0, 0)
    if not is_bit(sc, SYSTEM_CONFIG_EEP_OFF):
        mylogs.warning("MEANWELL EEPROM WRITE BACK IS ENABLED.")
        if not is_bit(cfg.i_changed_my_config, 1):
            mylogs.warning("MEANWELL SYSTEM CONFIG BIT - TRY TO SET EEPROM WRITE OFF ...")
            cfg.i_changed_my_config = set_bit(cfg.i_changed_my_config, 1)  # save the try to prvent to try again and again

            sc = set_bit(int(sc), SYSTEM_CONFIG_EEP_OFF)
            dev.mwcandev.system_config(1, sc)
            sleep(0.3)
            sc = dev.mwcandev.system_config(0, 0)
            if not is_bit(sc, SYSTEM_CONFIG_EEP_OFF):
                mylogs.warning("MEANWELL SYSTEM CONFIG BIT - COULD NOT SET EEPROM WRITE OFF")
                mylogs.warning("MEANWELL EEPROM WRITE IS STILL ENABLED. WITH A FIRMWARE > April / 2024 THIS CAN BE DISABLED")
            else:
                status.MW_EEPromOff = 1
                mylogs.warning("MEANWELL SYSTEM CONFIG BIT - EEPROM WRITE NOW IS DISABLED")
                mylogs.warning("YOU HAVE TO POWER CYCLE OFF/ON THE MEANWELL DEVICE NOW BY YOURSELF !!")
                MW_EEPROM_Counter_INC(0, 1)
                sys.exit(1)
    else:
        status.MW_EEPromOff = 1
        mylogs.info("MEANWELL SYSTEM CONFIG - EEPROM WRITE IS DISABLED")

##### Meanwell init end ##################


# Init Constatnt Based Charger
if cfg.Selected_Device_Charger == 2:
    mylogs.verbose("CONSTANT BASED CHARGER SETUP")
    cbc = ChargerConstBased(cfg.CBC_devid, cfg.CBC_ipadr, cfg.CBC_user, cfg.CBC_pass, cfg.loglevel)
    cbc.PowerOff()
    status.ChargerStatus = 0

# Init mPSU Charger
if cfg.Selected_Device_Charger == 10:
    try:
        if cfg.mPSU_interface == 0:
            dev.mPSU = mPSUcan(cfg.mPSU_device, cfg.loglevel)
            dev.mPSU.network_start()
        else:
            dev.mPSU = mPSUrs485(0, cfg.mPSU_device,cfg.loglevel)


        for x in range(cfg.mPSU_count):
            if x == 0: n = cfg.mPSU1_nodeid
            if x == 1: n = cfg.mPSU2_nodeid
            if x == 2: n = cfg.mPSU3_nodeid
            if x == 3: n = cfg.mPSU4_nodeid

            dev.mPSU.node_add(n)
            mylogs.info("FOUND DEVICE: " + dev.mPSU.devices[n].devname)
            # Turn device off
            mylogs.info("SET DEVICE OFF")
            dev.mPSU.operation(1, 0, n)

            # check autostart
            rval = dev.mPSU.autostart(0, 0, n)
            if rval == 1:
                mylogs.info("DISABLE AUTOSTART: " + str(rval))
                dev.mPSU.autostart(1, 0, n)

            # Check parallel mode
            rval = dev.mPSU.psu_connect_mode(0, 0, n)
            if cfg.mPSU_count == 1:
                if rval != 0:
                    mylogs.info("SET DEVICE TO STANDALONE MODE")
                    rval = dev.mPSU.psu_connect_mode(1, 0, n)
            else:
                if rval != 1:
                    mylogs.info("SET DEVICE TO PARALLEL MODE")
                    rval = dev.mPSU.psu_connect_mode(1, 1, n)

        rval = dev.mPSU.voltage_out_rw(0, 0, cfg.mPSU1_nodeid)
        status.mPSU_ChargeVoltage = cfg.FixedChargeVoltage + cfg.mPSU_ChargeVoltCorr
        if rval != status.mPSU_ChargeVoltage:
            rval = dev.mPSU.voltage_out_rw(1, status.mPSU_ChargeVoltage, cfg.mPSU1_nodeid)
            mylogs.info("SET CHARGE VOLTAGE: " + str(rval))
        else:
            mylogs.info("CHARGE VOLTAGE ALREADY SET: " + str(rval))

    except Exception as e:
        dev.mPSU.network_stop()  # Exception -> close the bus
        dev.mPSU = None
        mylogs.error("\n\nEXCEPTION mPSU Device not found !\n")
        mylogs.error(str(e))
        sys.exit(1)

#################################################################
#################################################################
############  D I S C H A R G E R - S E C T I O N  ##############
#################################################################
#################################################################

# Lumentree / Trucki init
if (cfg.Selected_Device_DisCharger == 1) or (cfg.lt_foreceoffonstartup == 1):
    # Init and get get Type of device
    mylogs.info("Lumentree Init discharger ...")

    if cfg.Selected_Device_DisCharger == 1:  # only if LT is really the DisCharger
        status.DisCharger_efficacy_factor = cfg.lt_efficacy_factor

    if (cfg.Selected_Device_DisCharger != 1) and (cfg.lt_foreceoffonstartup == 1):
        mylogs.info("Lumentree Init FORCE OFF MODE ...")

    try:
        dev.LT1 = lt232(cfg.lt_devtype, cfg.lt1_device, cfg.lt1_address, cfg.loglevel + 5)  # log+5 minimalmodbus dont use verbose
        dev.LT1.lt232_open()
        sleep(0.2)
        status.LT1_Temperature = int(dev.LT1.readtemp())
        sleep(0.2)
        mylogs.debug("LT1 temperature: " + str(status.LT1_Temperature))
        mylogs.debug("LT1 set output to 0")
        dev.LT1.set_watt_out(0)  # init with 0 #init with 0, force without any function above
        sleep(0.3)
        cfg.MaxDisChargeWATT = cfg.lt1_maxwatt
    except Exception as e:
        mylogs.error("\n\nLumentree Device 1 not found !\n")
        mylogs.error(str(e))
        if (cfg.Selected_Device_DisCharger != 1) and (cfg.lt_foreceoffonstartup == 1):
            mylogs.info("Lumentree Init FORCE OFF MODE ASSUME NOT PRESENT -> CONTINUE !")
        else:
            printlcd("EXCEPTION Lumentree1", str(e))
            sys.exit(1)

    if cfg.lt_count > 1:
        try:
            dev.LT2 = lt232(cfg.lt_devtype, cfg.lt2_device, cfg.lt2_address, cfg.loglevel + 5)  # log+5 minimalmodbus dont use verbose
            dev.LT2.lt232_open()
            status.LT2_Temperature = int(dev.LT2.readtemp())
            sleep(0.2)
            mylogs.debug("LT2 temperature: " + str(status.LT2_Temperature))
            mylogs.debug("LT2 set output to 0")
            dev.LT2.set_watt_out(0)  # init with 0, force without any function above
            sleep(0.2)
            cfg.MaxDisChargeWATT = cfg.MaxDisChargeWATT + cfg.lt2_maxwatt
        except Exception as e:
            mylogs.error("\n\nLumentree Device 2 not found !\n")
            mylogs.error(str(e))
            printlcd("EXCEPTION Lumentree2", str(e))
            sys.exit(1)

    if cfg.lt_count > 2:
        try:
            dev.LT3 = lt232(cfg.lt_devtype, cfg.lt3_device, cfg.lt3_address, cfg.loglevel + 5)  # log+5 minimalmodbus dont use verbose
            dev.LT3.lt232_open()
            status.LT3_Temperature = int(dev.LT3.readtemp())
            sleep(0.2)
            mylogs.debug("LT3 temperature: " + str(status.LT3_Temperature))
            mylogs.debug("LT3 set output to 0")
            dev.LT3.set_watt_out(0)  # init with 0 #init with 0, force without any function above
            sleep(0.2)
            cfg.MaxDisChargeWATT = cfg.MaxDisChargeWATT + cfg.lt3_maxwatt
        except Exception as e:
            mylogs.error("\n\nLumentree Device 3 not found !\n")
            mylogs.error(str(e))
            printlcd("EXCEPTION Lumentree3", str(e))
            sys.exit(1)

    if cfg.Selected_Device_DisCharger == 1:
        Lumentree_Check()  # Get The first voltage needed for later if Lumentree is used
    mylogs.info("MaxDisChargeWATT LT_calc.  : " + str(cfg.MaxDisChargeWATT))

#################################################################
# Soyo
if cfg.Selected_Device_DisCharger == 2:
    # Init and get get Type of device
    mylogs.info("Soyo Init discharger ...")

    status.DisCharger_efficacy_factor = cfg.soyo_efficacy_factor

    try:
        dev.soyo = soyo485(cfg.soyo_device, cfg.loglevel + 5)  # log+5 minimalmodbus dont use verbose
        dev.soyo485_open()
        sleep(0.3)
        cfg.MaxDisChargeWATT = cfg.soyo_maxwatt
    except Exception as e:
        mylogs.error("\n\nSoyo Device not found !\n")
        mylogs.error(str(e))
        printlcd("EXCEPTION Soyo", str(e))
        sys.exit(1)

#################################################################
# Discharge Simulator
if cfg.Selected_Device_DisCharger == 255:
    mylogs.info("DISCHARGE Simulator used")

# calculate the multiplyer for the DisCharger_efficacy_factor
# is needed in % --> 94% = 6% loss --> need 1.06% more current to get the output
status.DisCharger_efficacy_factor = (200 - status.DisCharger_efficacy_factor) / 100
mylogs.info("DisCharger_efficacy_factor  : " + str(status.DisCharger_efficacy_factor))


#################################################################
#################################################################
############  B M S - S E C T I O N  ############################
#################################################################
#################################################################
# BMS INIT
if cfg.Selected_BMS != 0:
    BMSstatus = BMS()
    mylogs.info("Init BMS ...")
    if cfg.Selected_BMS == 2:
        try:
            dev.jk = jkbms(cfg.BMS_device, cfg.loglevel)
            dev.jk.jkbms_open()
        except Exception as e:
            mylogs.error("\n\nJK BMS not found !\n")
            mylogs.error(str(e))
            printlcd("EXEPTION JKBMS", str(e))
            sys.exit(1)

    if cfg.Selected_BMS == 3:
        try:
            dev.daly = dalybmslib(cfg.BMS_device, cfg.BMS_daly_use_sinowealth, cfg.loglevel)
            dev.daly.dalybms_open()
        except Exception as e:
            mylogs.error("\n\nDALY BMS not found !\n")
            mylogs.error(str(e))
            printlcd("EXEPTION DALY BMS", str(e))
            sys.exit(1)

    if cfg.Selected_BMS == 100:
        try:
            dev.sasb = standalone_serialbattery(cfg.BMS_device, cfg.SASBBMSType, cfg.SASBBMSAdr, cfg.loglevel)
            dev.sasb.bms_open()
            sleep(0.5)
        except Exception as e:

            mylogs.error("\n\nSASBBMS not found !\n")
            mylogs.error(str(e))
            printlcd("EXEPTION SASBBMS", str(e))
            sys.exit(1)

    sleep(1)  # wait until bus is ready

# Now the Battery hardware should be initilized
# Read the first battery value to initilize voltage and BMS
# Just check all sources.
i = 1
while ((status.BatteryVoltage == 0)) and (i < 10):  # or (status.BMSSOC == 0)
    GetBMSData()
    GetChargerVoltage()
    GetDisChargerVoltage()
    GetBatteryVoltage()
    mylogs.info("Try to get Voltage and BMSSOC ...: " + str(i) + " Voltage: " + str(status.BatteryVoltage / 100) + "V - BMSSOC: " + str(status.BMSSOC) + "%")
    i += 1
    sleep(1)

if i >= 10:
    mylogs.error("ERROR CAN NOT GET BATTERY VOLTAGE AND BMSSOC - STOP")
    sys.exit(1)

#################################################################
#################################################################
############  G P I O - S E C T I O N  ##########################
#################################################################
#################################################################
# GPIO Init
if cfg.Use_GPIO != 0:
    GPIO.setmode(GPIO.BCM)
    if cfg.gpio1 != 0:
        mylogs.info("GPIO INIT: GPIO1: " + str(cfg.gpio1))
        GPIO.setup(cfg.gpio1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(cfg.gpio1, GPIO.FALLING, callback=gpio_callback, bouncetime=1000)

    if cfg.gpio2 != 0:
        mylogs.info("GPIO INIT: GPIO2: " + str(cfg.gpio2))
        GPIO.setup(cfg.gpio2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(cfg.gpio2, GPIO.FALLING, callback=gpio_callback, bouncetime=1000)

    if cfg.gpio3 != 0:
        mylogs.info("GPIO INIT: GPIO3: " + str(cfg.gpio3))
        GPIO.setup(cfg.gpio3, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(cfg.gpio3, GPIO.FALLING, callback=gpio_callback, bouncetime=1000)

    if cfg.gpio4 != 0:
        mylogs.info("GPIO INIT: GPIO4: " + str(cfg.gpio4))
        GPIO.setup(cfg.gpio4, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(cfg.gpio4, GPIO.FALLING, callback=gpio_callback, bouncetime=1000)

#################################################################
#################################################################
############  U S E R  - E X T E R N A A L#######################
#################################################################
#################################################################
# User can do someting for his own setup
# WARNING you should know what you are doing !
status = bs_ext.ext_open(dev, cfg, status)

#################################################################
#################################################################
############  M E T E R - S E C T I O N  ########################
#################################################################
#################################################################
# mqtt init
if (cfg.GetPowerOption == 0) or (cfg.mqttpublish == 1):
    #    global mqttclient

    try:
        mylogs.info("USE MQTT, Init ...")
        dev.mqttclient = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="BatteryController",
            clean_session=False,
        )
        # dev.mqttclient = mqtt.Client(client_id="BatteryController",clean_session=False) #mqtt < 2.00
        dev.mqttclient.on_connect = mqtt_on_connect
        dev.mqttclient.on_disconnect = mqtt_on_disconnect
        dev.mqttclient.on_subscribe = mqtt_on_subscribe
        if cfg.GetPowerOption == 0:
            dev.mqttclient.on_message = mqtt_on_message

        dev.mqttclient.connect_timeout = 600  # Wait in case of restart / blackout until mqtt server is ready
        dev.mqttclient.username_pw_set(cfg.mqttuser, cfg.mqttpass)
        dev.mqttclient.connect(cfg.mqttserver, port=cfg.mqttport, keepalive=60)
        dev.mqttclient.loop_start()
    except Exception as e:
        mylogs.error("MQTT EXCEPTION !")
        mylogs.error(str(e))
        printlcd("EXCEPTION MQTT", str(e))
        sys.exit(1)


#################################################################
# http get init
if cfg.GetPowerOption == 1:
    try:
        mylogs.info("USE HTTP for Meter: " + str(cfg.http_get_option))
        schedule.every(cfg.http_schedule_time).seconds.do(http_request)  # Start every Xs
        METER = meter(
            cfg.http_get_option,
            cfg.http_ip_address,
            cfg.http_ip_port,
            cfg.http_user,
            cfg.http_pass,
            cfg.http_vzl_UUID,
            cfg.http_emlog_meterindex,
            cfg.http_iobrogerobject,
            cfg.loglevel,
        )
    except Exception as e:
        mylogs.error("METER INIT EXCEPTION !")
        mylogs.error(str(e))
        sys.exit(1)

#################################################################
# Simulator
if cfg.GetPowerOption == 255:
    schedule.every(2).seconds.do(simulator_request)  # Start every 2s
    mylogs.debug("USE SIMULATOR for Meter")

#################################################################
# Start WebServer
if cfg.Use_WebServer == 1:
    try:
        server_class = HTTPServer
        handler_class = WS
        server_address = (cfg.WSipadr, cfg.WSport)
        httpd = server_class(server_address, handler_class)
        httpd.socket.settimeout(0.1)  # Prevent blocking the rest of the script
        mylogs.info("WEBSERVER START at port: " + str(cfg.WSport))

    except Exception as e:
        mylogs.error("EXCEPTION STARTING WEBSERVER")
        mylogs.error(str(e))
        sys.exit(1)

#################################################################
#################################################################
############  M A I N  - S E C T I O N  #########################
#################################################################
#################################################################
while True:
    if cfg.Use_WebServer == 1:
        httpd.handle_request()  # handle webserver requests
    if (cfg.GetPowerOption == 1) or (cfg.GetPowerOption == 255):
        schedule.run_pending()
    sleep(0.05)  # prevent high CPU usage
