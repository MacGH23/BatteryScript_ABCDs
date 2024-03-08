#!/usr/bin/env python3

# Script for automatic charging and discharge your Battery 
# Not suitable for productive use. 
# Use for demo purposes only !
# Use on own risk !

##########################################################################################
# Needed external python3 modules use pip or pip3 depands on your environment
# pip3 install pyserial
# pip3 install paho-mqtt
# pip3 install ifcfg
# pip3 install minimalmodbus
# pip3 install configupdater
# pip3 install psutil
##########################################################################################
# Hints
# For the serial communication the user must be added to dialout group
# sudo usermod -a -G tty $USER
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


from Charger.mwcan import *
from DisCharger.lt232 import *
from BMS.jkbms import *
from Meter.meter import *

#LCD import
from LCD.hd44780_i2c import i2clcd

#######################################################################
# WEBSERVER CLASS #####################################################
#######################################################################

class WS(BaseHTTPRequestHandler):

        def _set_headers(self):
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            return

        def _gettableentry(self, parameter,value):
            Button = 'n.a.'
            if((parameter=='ChargerEnabled') or (parameter=='DisChargerEnabled') or (parameter=='WebAutoRefresh')):
                Button = f'<form action="/" method="post"><button name={parameter} type="submit" value={parameter}>Toggle ON/OFF</button></form>'

            if((parameter=='EstBatteryWh')):
                Button = f'<form action="/" method="post"><button name={parameter} type="submit" value={parameter}>Reset to 0</button></form>'

            if((parameter=='Reboot') or (parameter=='Shutdown') or ('Restart' in parameter)):
                Button = f'<form action="/" method="post"><button name={parameter} type="submit" value={parameter}>Press 3 times</button></form>'

                      #f'<input type="text" name="EstBatteryWhValue" placeholder="{value}">' + \
                      #'<label for="Minwatt">Minwatt:</label>\n'+ \
                      #'<input type="text" id="Minwatt" name="Minwatt"><br><br>\n'+ \
                      #'<button type="submit">Submit</button>\n'+ \
                      #'<button type="submit" formmethod="post">Submit using POST</button>\n' + \

            tabcontent = '<tr>\n'+ \
                        f'<td style="border-style: solid; border-width: 1px;"><p>{parameter}</p></td>\n' + \
                        f'<td style="border-style: solid; width: 50px; text-align: center; border-width: 1px;">{value}</td>\n'            + \
                        f'<td style="border-style: solid; border-width: 1px;">{Button}</td>\n'           + \
                         '</tr>\n'

            return tabcontent

        def _beginhtml(self, message, refreshtime, pagepath):
            if(status.WebAutoRefresh == 0):
                refreshtime = -1

            content = '<!DOCTYPE HTML>\n' + \
                      '<html>\n' + \
                      '<head>\n' + \
                      f'<meta http-equiv="refresh" content="{refreshtime}">\n' + \
                      '<title>ABCDs Script Web Server</title>\n' + \
                      f'<base href={cfg.WSipadr}:{cfg.WSport}/"  target="_parent"/>\n' + \
                      '</head>\n' + \
                      '<body>\n' + \
                      '<h1>Welcome to ABCDs WebServer Interface - WIP</h1>\n' + \
                      '<p style="font-size:1.4vw;">Links: &nbsp;<a href="/">Show global Status</a>&nbsp;&nbsp;&nbsp;' + \
                      '<a href="/config">Show Config</a>&nbsp;&nbsp;&nbsp;' + \
                      '<a href="/bms">Show BMS status</a>&nbsp;&nbsp;&nbsp;' + \
                      '<a href="/system">Show System Status</a>&nbsp;&nbsp;&nbsp;</p>' + \
                      '<br><br>\n<b>' + \
                      message + \
                      '</b></h1><br>\n'

            """
                      f'<form action="{pagepath}" method="post"><button name=Refresh type="submit" value=Refresh>Refresh site</button></form>'+\
                      message + \
                      '</b></h1><br>\n'
            """

            return content

        def _endhtml(self):
            content = '</body>\n' + \
                      '</html>\n'
            return content 

        def _confightml(self, message):
            content = ''
            for attr, value in vars(cfg).items():
                content = content + self._gettableentry(attr,value)

            content = self._beginhtml(message,-1,'/config') + \
                      '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;font-size:1.1vw;">'+ \
                      '<tbody>'+ \
                      content + \
                      '</tbody>' + \
                      '</table>'+ \
                      self._endhtml()

            return content.encode("utf8")  # NOTE: must return a bytes object!

        def _bmshtml(self, message):
            content = ''
            for attr, value in vars(BMSstatus).items():
                #if((attr == "BMSCurrent") or (attr == "BMSVoltage")): attr = str(int(attr)/100)
                content = content + self._gettableentry(attr,value)

            content = self._beginhtml(message,30,'/bms') + \
                      '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;font-size:1.1vw;">'+ \
                      '<tbody>'+ \
                      content + \
                      '</tbody>' + \
                      '</table>'+ \
                      self._endhtml()

            return content.encode("utf8")  # NOTE: must return a bytes object!

        def _systemhtml(self, message):
            content = self._gettableentry('CPU usage in %',psutil.cpu_percent()) +\
                      self._gettableentry('RAM usage in %',psutil.virtual_memory().percent) +\
                      self._gettableentry('Reboot',status.WebRebootSDcounter)   +\
                      self._gettableentry('Shutdown',status.WebRebootSDcounter) +\
                      self._gettableentry('Restart0',status.WebRebootSDcounter) +\
                      self._gettableentry('Restart1',status.WebRebootSDcounter) +\
                      self._gettableentry('Restart2',status.WebRebootSDcounter) +\
                      self._gettableentry('Restart3',status.WebRebootSDcounter)

            content = self._beginhtml(message,-1,'/system') + \
                      '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;font-size:1.1vw;">'+ \
                      '<tbody>'+ \
                      content + \
                      '</tbody>' + \
                      '</table>'+ \
                      self._endhtml()

            return content.encode("utf8")  # NOTE: must return a bytes object!

        def _statushtml(self, message):
            content = self._beginhtml(str(message),30,'/') + \
                      '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;font-size:1.1vw;">\n'+ \
                      '<tbody>\n'+ \
                      self._gettableentry('CurrentWattValue',status.CurrentWattValue) + \
                      self._gettableentry('CurrentTotalWatt',status.CurrentTotalWatt) + \
                      self._gettableentry('CurrentAverageWatt',status.CurrentAverageWatt) + \
                      self._gettableentry('LastWattValueUsedinDevice',status.LastWattValueUsedinDevice) + \
                      self._gettableentry('BatteryVoltage',status.BatteryVoltage/100) + \
                      self._gettableentry('BMSSOC',status.BMSSOC) + \
                      self._gettableentry('EstBatteryWh',round(status.EstBatteryWh/1000)) + \
                      self._gettableentry('BatteryFull',status.BatteryFULL) + \
                      self._gettableentry('BatteryEmpty',status.BatteryEMPTY) + \
                      self._gettableentry('ChargerEnabled',status.ChargerEnabled) + \
                      self._gettableentry('DisChargerEnabled',status.DisChargerEnabled) + \
                      self._gettableentry('MW_NPB_COUNTER',cfg.MW_NPB_COUNTER) + \
                      self._gettableentry('MW_BIC_COUNTER',cfg.MW_BIC_COUNTER) + \
                      self._gettableentry('WebAutoRefresh',status.WebAutoRefresh) + \
                      '</tbody>\n' + \
                      '</table>\n'+ \
                      '</form>\n' + \
                      self._endhtml()

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
            if(self.path == '/'):
                self.wfile.write(self._statushtml("Read Status"))
            if(self.path == '/config'):
                self.wfile.write(self._confightml("Read Global Config"))
            if(self.path == '/bms'):
                self.wfile.write(self._bmshtml("Read BMS status"))
            if(self.path == '/system'):
                self.wfile.write(self._systemhtml("Read System status"))
            if('/DIRECTRESTART' in self.path):
                n = self.path[-1]
                self.wfile.write(self._statushtml("DIRECTRESTART ! NR " + str(n)))
                subprocess.Popen([sys.executable, 'BSstart.py',n], start_new_session=True)
                sys.exit(1)

            return

        def do_HEAD(self):
            self._set_headers()
            return

        def do_POST(self):
            mylogs.debug("WebServer: POST")
            self._set_headers()
            todo = ''

            content_length = int(self.headers['Content-Length'])
            bodybytes = self.rfile.read(content_length)
            bodystr   = bodybytes.decode("UTF-8")
            bodyitem  = bodystr.split('&')

            bodyitems = {}
            for item in bodyitem:
                variable, value = item.split('=')
                bodyitems[variable] = value
                mylogs.info("WebServer: " + variable + ' - ' + value)

                if(variable == 'ChargerEnabled'):
                    mylogs.info("WebServer: ChargerEnabled button pressed")
                    todo = 'ChargerEnabled Toggle done'
                    status.ChargerEnabled = 1 - status.ChargerEnabled
                    self.wfile.write(self._statushtml(todo))

                if(variable == 'DisChargerEnabled'):
                    mylogs.info("WebServer: DisChargerEnabled button pressed")
                    todo = 'DisChargerEnabled Toggle done'
                    status.DisChargerEnabled = 1 - status.DisChargerEnabled
                    self.wfile.write(self._statushtml(todo))

                if(variable == 'WebAutoRefresh'):
                    mylogs.info("WebAutoRefresh button pressed")
                    todo = 'WebAutoRefresh Toggle done'
                    status.WebAutoRefresh = 1 - status.WebAutoRefresh
                    self.wfile.write(self._statushtml(todo))

                if(variable == 'EstBatteryWh'):
                    mylogs.info("EstBatteryWh reset button pressed")
                    todo = 'EstBatteryWh reset to 0 done'
                    status.EstBatteryWh = 0
                    self.wfile.write(self._statushtml(todo))

                if(variable == 'Reboot'):
                    status.WebRebootSDcounter += 1
                    todo = 'Press 3 times to reboot: ' + str(status.WebRebootSDcounter)
                    if(status.WebRebootSDcounter == 3):
                        todo = 'Reboot now ...'
                        self.wfile.write(self._systemhtml(todo))
                        on_exit()
                        os.system('sudo reboot')
                    self.wfile.write(self._systemhtml(todo))

                if(variable == 'Shutdown'):
                    status.WebRebootSDcounter += 1
                    todo = 'Press 3 times to shutdown: ' + str(status.WebRebootSDcounter)
                    if(status.WebRebootSDcounter == 3):
                        todo = 'Shutdown !'
                        self.wfile.write(self._systemhtml(todo))
                        on_exit()
                        os.system('sudo shutdown -P now')
                    self.wfile.write(self._systemhtml(todo))

                if('Restart' in variable):
                    n = variable[-1] 
                    status.WebRebootSDcounter += 1
                    todo = 'Press 3 times to use Restart Method ' + n + ': ' + str(status.WebRebootSDcounter)
                    if(status.WebRebootSDcounter == 3):
                        todo = 'Execute Restart Method ' + n + ' !'
                        self.wfile.write(self._systemhtml(todo))
                        subprocess.Popen([sys.executable, 'BSstart.py',n], start_new_session=True)
                        sys.exit(1)
                    self.wfile.write(self._systemhtml(todo))

            return

        def log_request(self, code=None, size=None):
            host, port = self.client_address[:2]
            mylogs.info('<-> HTTP Request from: ' + host + ' - Site: ' + self.path)

#        def log_message(self, format, *args):
#            print('Message')


#######################################################################
# WEBSERVER CLASS END #################################################
#######################################################################


#########################################
##class config
class BMS:
    def __init__(self):
        self.BMSSOC                     = 0 # Battery State of Charge status if BMS is used, if not 100% is used
        self.BMSCurrent                 = 0
        self.BMSVoltage                 = 0 # Voltage of BMS
        self.BMSTemp_Mosfet             = 0
        self.BMSTemp1                   = 0
        self.BMSTemp2                   = 0
        self.CellCount                  = 0
        self.BMSCellVoltage             = []
        for x in range(24):
            self.BMSCellVoltage.append(x)
            self.BMSCellVoltage[x]      = 0

class Devicestatus:

    def __init__(self):
        self.configfile                 = ""
        self.LastMeterTime              = datetime.datetime.now()     #init with start time
        self.ChargerEnabled             = 1   # for remote enable and disable
        self.DisChargerEnabled          = 1   # for remote enable and disable
        self.CurrentWattValue           = 0   # from Meter
        self.CurrentTotalWatt           = 0   # Used for Device charger or discharger; -x = SOLAR, +x = GRID
        self.CurrentAverageWatt         = 0   # Current calculated Average Watt 
        self.LastWattValueUsedinDevice  = 0   # Used in the Device charger or discharger; -x = SOLAR, +x = GRID depends on max min vlaues
        self.LastChargerSetCurrent      = 0
        self.LastChargerGetCurrent      = 0
        self.LastDisChargerCurrent      = 0
        self.BICChargeDisChargeMode     = 0   # 0=Charge, 1 = DisCharge
        self.LastChargerMode            = 0
        self.ChargerStatus              = 0
        self.DisChargerStatus           = 0
        self.ChargerMainVoltage         = 0 #must be set during init of the charger to 12V, 24V, 48V or 92V
        self.ZeroExportWatt             = 0
        self.ZeroImportWatt             = 0
        self.BatteryFULL                = 0   #0=no, 1=Full
        self.BatteryEMPTY               = 0   #0=no, 1=EMPTY
        self.BatteryVoltage             = 0   # Battery Voltage to check charging status, this is used for calculation 
        self.BMSSOC                     = 100 # Battery State of Charge status if BMS is used, if not 100% is used
        self.BMSCurrent                 = 0
        self.BMSVoltage                 = 0   # Voltage of BMS
        self.EstBatteryWh               = 0
        self.ChargerVoltage             = 0   # Voltage of Charger
        self.DisChargerVoltage          = 0   # Voltage of DisCharger
        self.ProcessCount               = 18  # only all 20 conts, mqtt sends every 2 seconds --> 40 Seconde, start with 15 to have the first read after 10seconds
        self.LastPowerArrayPosition     = -1  # increase in first step --> 1st entry is 0
        self.actchargercounter          = 100   # only change values after x METER values --> all 2 Seconds new value with chargercounter = 5 => 10seconds, first start ok -> 100
        self.waitchargercounter         = 0
        self.DisCharger_efficacy_factor = float(0)
        self.WebAutoRefresh             = 0
        self.WebRebootSDcounter         = 0
        self.LT1_Temperature            = 0
        self.LT2_Temperature            = 0
        self.LT3_Temperature            = 0
        self.MW_NPB_Temperature         = 0
        self.MW_BIC_Temperature         = 0

class chargerconfig:

    def iniread(self):
        try:
            updater = ConfigUpdater()
            updater.read(status.configfile)

            self.loglevel       = int(updater["Setup"]["loglevel"].value)
            self.logpath        = str(updater["Setup"]["logpath"].value)
            self.logtoconsole   = int(updater["Setup"]["logtoconsole"].value)
            self.logtofile      = int(updater["Setup"]["logtofile"].value)
            self.logappendfile  = int(updater["Setup"]["logappendfile"].value)
            self.logtosyslog    = int(updater["Setup"]["logtosyslog"].value)

            mylogs.setLevel(self.loglevel)

            if (self.logtofile == 1):
                if self.logappendfile == 1:
                    filehandler = logging.FileHandler(self.logpath, mode='a')
                else:
                    filehandler = logging.FileHandler(self.logpath, mode='w')
                    #filehandler = logging.handlers.RotatingFileHandler(self.logpath, mode='w', backupCount=2)
                    #filehandler = logging.handlers.TimedRotatingFileHandler(self.logpath, when='midnight', backupCount=7, utc=False)
                    #filehandler = logging.handlers.TimedRotatingFileHandler(self.logpath, when='midnight', backupCount=7, encoding=None, delay=False, utc=False, atTime=None, errors=None)

                filehandler.setLevel(self.loglevel)
                fileformat = logging.Formatter("%(asctime)s:%(module)s:%(levelname)s:%(message)s",datefmt="%H:%M:%S")
                filehandler.setFormatter(fileformat)
                mem = logging.handlers.MemoryHandler(10*1024,30,filehandler,flushOnClose=True)
                mylogs.addHandler(mem)

            if (self.logtoconsole == 1):
                stream = logging.StreamHandler()
                stream.setLevel(self.loglevel)
                streamformat = logging.Formatter("%(asctime)s:%(module)s:%(levelname)s:%(message)s",datefmt="%H:%M:%S")
                stream.setFormatter(streamformat)
                mylogs.addHandler(stream)

            if (self.logtosyslog == 1):
                slhandler = SysLogHandler(facility=SysLogHandler.LOG_DAEMON,address='/dev/log')
                slformat = logging.Formatter("%(asctime)s:%(module)s:%(levelname)s:%(message)s",datefmt="%Y-%m-%d %H:%M:%S")
                handler.setFormatter(slformat)
                logger.addHandler(slhandler)

            mylogs.debug("Read config ...")

            self.i_changed_my_config       =  int(updater["Setup"]["i_changed_my_config"].value)
            self.ChargerPowerCalcCount     =  int(updater["Setup"]["ChargerPowerCalcCount"].value)
            self.DisChargerPowerCalcCount  =  int(updater["Setup"]["DisChargerPowerCalcCount"].value)
            status.powercalccount = self.ChargerPowerCalcCount

            self.CellCount                 =  int(updater["Setup"]["CellCount"].value)
            self.CellAH                    =  int(updater["Setup"]["CellAH"].value)
            self.CellvoltageMax            =  int(updater["Setup"]["CellvoltageMax"].value)
            self.CellvoltageMin            =  int(updater["Setup"]["CellvoltageMin"].value)
            self.CellvoltageMaxRestart     =  int(updater["Setup"]["CellvoltageMaxRestart"].value)
            self.CellvoltageMinRestart     =  int(updater["Setup"]["CellvoltageMinRestart"].value)

            self.FixedChargeVoltage        =  self.CellCount * self.CellvoltageMax
            self.StopDischargeVoltage      =  self.CellCount * self.CellvoltageMin
            self.RestartChargevoltage      =  self.CellCount * self.CellvoltageMaxRestart
            self.RestartDisChargevoltage   =  self.CellCount * self.CellvoltageMinRestart
            self.RestartDisChargevoltage   =  self.CellCount * self.CellvoltageMinRestart
            self.BatteryTotalWH            =  round(self.CellCount * self.CellAH * 3.2 * 1000)

            self.MaxChargeCurrent          =  int(updater["Setup"]["MaxChargeCurrent"].value)
            self.MinChargeCurrent          =  int(updater["Setup"]["MinChargeCurrent"].value)
            self.MaxDisChargeCurrent       =  int(updater["Setup"]["MaxDisChargeCurrent"].value)
            self.MinDisChargeCurrent       =  int(updater["Setup"]["MinDisChargeCurrent"].value)
            self.ChargerCurrentDiffHyst    =  int(updater["Setup"]["ChargerCurrentDiffHyst"].value)
            self.DisChargerCurrentMin      =  int(updater["Setup"]["DisChargerCurrentMin"].value)
            self.MaxChargeWATT             =  int(updater["Setup"]["MaxChargeWATT"].value)
            self.MinChargeWATT             =  int(updater["Setup"]["MinChargeWATT"].value)
            self.LastChargePower_delta     =  int(updater["Setup"]["LastChargePower_delta"].value)

            self.StopMinChargeCurrent      =  int(updater["Setup"]["StopMinChargeCurrent"].value)
            self.MaxDisChargeWATT          =  int(updater["Setup"]["MaxDisChargeWATT"].value)
            self.MinDisChargeWATT          =  int(updater["Setup"]["MinDisChargeWATT"].value)
            self.ZeroDeltaChargerWatt      =  int(updater["Setup"]["ZeroDeltaChargerWatt"].value)
            self.ZeroDeltaDisChargeWATT    =  int(updater["Setup"]["ZeroDeltaDisChargeWATT"].value)
            self.MeterUpdateChargeCounter  =  int(updater["Setup"]["MeterUpdateChargeCounter"].value)
            self.MeterUpdateDisChargeCounter=  int(updater["Setup"]["MeterUpdateDisChargeCounter"].value)
            self.MW_NPB_COUNTER            =  int(updater["Setup"]["MW_NPB_COUNTER"].value)
            self.MW_BIC_COUNTER            =  int(updater["Setup"]["MW_BIC_COUNTER"].value)
            self.BatteryVoltageSource      =  int(updater["Setup"]["BatteryVoltageSource"].value)
            self.BatteryVoltageCorrection  =  int(updater["Setup"]["BatteryVoltageCorrection"].value)
            self.EstBatteryWh              =  int(updater["Setup"]["EstBatteryWh"].value)

            self.LastDisChargePower_delta  =  int(updater["Setup"]["LastDisChargePower_delta"].value)
            self.Voltage_ACIN_correction   =  int(updater["Setup"]["Voltage_ACIN_correction"].value)

            self.Selected_Device_Charger   =  int(updater["Setup"]["Selected_Device_Charger"].value)
            self.Selected_Device_DisCharger=  int(updater["Setup"]["Selected_Device_DisCharger"].value)
            self.USEDID                    =  updater["Setup"]["USEDID"].value
            self.ForceBicAlwaysOn          =  int(updater["Setup"]["ForceBicAlwaysOn"].value)
            self.BIC2200_efficacy_factor   =  int(updater["Setup"]["BIC2200_efficacy_factor"].value)
            self.MW_NPB_ChargeVoltCorr     =  int(updater["Setup"]["MW_NPB_ChargeVoltCorr"].value)
            self.MW_BIC_ChargeVoltCorr     =  int(updater["Setup"]["MW_BIC_ChargeVoltCorr"].value)
            self.MW_BIC_DisChargeVoltCorr  =  int(updater["Setup"]["MW_BIC_DisChargeVoltCorr"].value)
            self.MW_BIC2200_MaxTemp        =  int(updater["Setup"]["MW_BIC2200_MaxTemp"].value)
            self.MW_NPB_MaxTemp            =  int(updater["Setup"]["MW_NPB_MaxTemp"].value)

            self.StopOnConnectionLost      =  int(updater["Setup"]["StopOnConnectionLost"].value)
            self.GetPowerOption            =  int(updater["Setup"]["GetPowerOption"].value)
            self.PowerControlmethod        =  int(updater["Setup"]["PowerControlmethod"].value)

            self.http_schedule_time        =  int(updater["Setup"]["http_schedule_time"].value)

            self.http_get_option           =  int(updater["Setup"]["http_get_option"].value)
            self.http_ip_address           =  updater["Setup"]["http_ip_address"].value
            self.http_ip_port              =  updater["Setup"]["http_ip_port"].value
            self.http_user                 =  updater["Setup"]["http_user"].value
            self.http_pass                 =  updater["Setup"]["http_pass"].value
            self.http_emlog_meterindex     =  updater["Setup"]["http_EMLOG_METERINDEX"].value
            self.http_vzl_UUID             =  updater["Setup"]["http_VZL_UUID"].value
            self.http_iobrogerobject       =  updater["Setup"]["http_iobrogerobject"].value


            self.lt_foreceoffonstartup     =  int(updater["Setup"]["lt_foreceoffonstartup"].value)
            self.lt_count                  =  int(updater["Setup"]["lt_count"].value)
            self.lt_efficacy_factor        =  int(updater["Setup"]["lt_efficacy_factor"].value)
            self.lt_MaxTemp                =  int(updater["Setup"]["lt_MaxTemp"].value)

            self.lt1_device                =  updater["Setup"]["lt1_device"].value
            self.lt1_address               =  int(updater["Setup"]["lt1_address"].value)
            self.lt1_maxwatt               =  int(updater["Setup"]["lt1_maxwatt"].value)

            self.lt2_device                =  updater["Setup"]["lt2_device"].value
            self.lt2_address               =  int(updater["Setup"]["lt2_address"].value)
            self.lt2_maxwatt               =  int(updater["Setup"]["lt2_maxwatt"].value)

            self.lt3_device                =  updater["Setup"]["lt3_device"].value
            self.lt3_address               =  int(updater["Setup"]["lt3_address"].value)
            self.lt3_maxwatt               =  int(updater["Setup"]["lt3_maxwatt"].value)

            self.mqttserver                =  updater["Setup"]["mqttserver"].value
            self.mqttport                  =  int(updater["Setup"]["mqttport"].value)
            self.mqttuser                  =  updater["Setup"]["mqttuser"].value
            self.mqttpass                  =  updater["Setup"]["mqttpass"].value
            self.mqttsubscribe             =  updater["Setup"]["mqttsubscribe"].value
            self.mqttpublish               =  int(updater["Setup"]["mqttpublish"].value)
            self.mqttpublishWATT           =  updater["Setup"]["mqttpublishWATT"].value
            self.mqttpublishSOC            =  updater["Setup"]["mqttpublishSOC"].value
            self.mqttpublishBatVolt        =  updater["Setup"]["mqttpublishBatVolt"].value
            self.mqttpublishWATTCut        =  int(updater["Setup"]["mqttpublishWATTCut"].value)

            self.Selected_BMS              =  int(updater["Setup"]["Selected_BMS"].value)
            self.bms_device                =  updater["Setup"]["bms_device"].value
            self.BMSminSOC                 =  int(updater["Setup"]["BMSminSOC"].value)
            self.BMSRestartSOC             =  int(updater["Setup"]["BMSRestartSOC"].value)
            self.BMS_MaxTempMosFet         =  int(updater["Setup"]["BMS_MaxTempMosFet"].value)
            self.BMS_MaxTemp1              =  int(updater["Setup"]["BMS_MaxTemp1"].value)
            self.BMS_MaxTemp2              =  int(updater["Setup"]["BMS_MaxTemp2"].value)

            self.Selected_LCD              =  int(updater["Setup"]["Selected_LCD"].value)
            self.lcdi2cadr                 =  int(updater["Setup"]["lcdi2cadr"].value)

            self.Use_GPIO                  =  int(updater["Setup"]["Use_GPIO"].value)
            self.gpio1                     =  int(updater["Setup"]["gpio1"].value)
            self.gpio2                     =  int(updater["Setup"]["gpio2"].value)
            self.gpio3                     =  int(updater["Setup"]["gpio3"].value)
            self.gpio4                     =  int(updater["Setup"]["gpio4"].value)

            self.Use_WebServer             =  int(updater["Setup"]["Use_WebServer"].value)
            self.WSport                    =  int(updater["Setup"]["WSport"].value)
            self.WSipadr                   =  updater["Setup"]["WSipadr"].value
            if(self.WSipadr == ""):
                try:  
                    self.WSipadr = subprocess.check_output(['hostname', '-I']).decode().split()[0]
                except Exception as e:
                    mylogs.error("EXCEPTION ON GETTING LOCAL IP ADDRESS - USE EMPTY ONE")
                    mylogs.error(str(e))
                    self.WSipadr = ""


            updater["Setup"]["MW_NPB_COUNTER_LAST"].value     = str(self.MW_NPB_COUNTER) + "_" + datetime.datetime.now().strftime("%d-%m-%Y, %H:%M")
            updater["Setup"]["MW_BIC_COUNTER_LAST"].value     = str(self.MW_BIC_COUNTER) + "_" + datetime.datetime.now().strftime("%d-%m-%Y, %H:%M")
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

            mylogs.info("MaxChargeCurrent:           " + str(self.MaxChargeCurrent))
            mylogs.info("MinChargeCurrent:           " + str(self.MinChargeCurrent))
            mylogs.info("ZeroDeltaChargerWatt:       " + str(self.ZeroDeltaChargerWatt))
            mylogs.info("MaxDisChargeCurrent:        " + str(self.MaxDisChargeCurrent))
            mylogs.info("ZeroDeltaDisChargeWATT:     " + str(self.ZeroDeltaDisChargeWATT))

            mylogs.info("LastDisChargePower_delta:   " + str(self.LastDisChargePower_delta))
            mylogs.info("Voltage_ACIN_correction:    " + str(self.Voltage_ACIN_correction))
            mylogs.info("ForceBicAlwaysOn:           " + str(self.ForceBicAlwaysOn))
            mylogs.info("BIC2000 efficacy_factor     " + str(self.BIC2200_efficacy_factor))

            mylogs.info("-- PowerMeter --            ")
            mylogs.info("GetPowerOption:             " + str(self.GetPowerOption))
            mylogs.info("MeterUpdateChargeCounter:   " + str(self.MeterUpdateChargeCounter))
            mylogs.info("MeterUpdateDisChargeCounter:" + str(self.MeterUpdateDisChargeCounter))
            mylogs.info("StopOnConnectionLost:       " + str(self.StopOnConnectionLost))

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
            mylogs.info("USEDID:                      " + str(self.USEDID))
            mylogs.info("MW_NPB_COUNTER:              " + str(self.MW_NPB_COUNTER))
            mylogs.info("MW_BIC_COUNTER:              " + str(self.MW_BIC_COUNTER))
            mylogs.info("MW_NPB_ChargeVoltCorr:       " + str(self.MW_NPB_ChargeVoltCorr))
            mylogs.info("MW_BIC_ChargeVoltCorr:       " + str(self.MW_BIC_ChargeVoltCorr))
            mylogs.info("MW_BIC_DisChargeVoltCorr:    " + str(self.MW_BIC_DisChargeVoltCorr))
            mylogs.info("MW_BIC2200_MaxTemp:          " + str(self.MW_BIC2200_MaxTemp))
            mylogs.info("MW_NPB_MaxTemp:              " + str(self.MW_NPB_MaxTemp))

            mylogs.info("-- Lumentree --             ")
            mylogs.info("Lumentree efficacy_factor   " + str(self.lt_efficacy_factor))
            mylogs.info("Lumentree Count             " + str(self.lt_count))
            mylogs.info("Lumentree lt_MaxTemp        " + str(self.lt_MaxTemp))

            mylogs.info("Lumentree device  1         " + self.lt1_device)
            mylogs.info("Lumentree address 1         " + str(self.lt1_address))
            mylogs.info("Lumentree device  2         " + self.lt2_device)
            mylogs.info("Lumentree address 2         " + str(self.lt2_address))
            mylogs.info("Lumentree device  3         " + self.lt3_device)
            mylogs.info("Lumentree address 3         " + str(self.lt3_address))

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
            mylogs.info("bms_device:                 " + str(self.bms_device))
            mylogs.info("BMSminSOC:                  " + str(self.BMSminSOC))
            mylogs.info("BMSRestartSOC:              " + str(self.BMSRestartSOC))
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
        updater = ConfigUpdater()
        updater.read(status.configfile)

        updater["Setup"]["MW_NPB_COUNTER"].value     = str(cfg.MW_NPB_COUNTER)
        updater["Setup"]["MW_BIC_COUNTER"].value     = str(cfg.MW_BIC_COUNTER)
        updater["Setup"]["EstBatteryWh"].value      = str(cfg.EstBatteryWh)
        updater.update_file()
        return

    def __init__(self):
      self.iniread()
      return

##########EXIT###############################################
def on_exit():
    try:
        mylogs.info("CLEAN UP ...")
        schedule.clear() #remove all schedules if exists or not
        if ((cfg.GetPowerOption==0) or (cfg.mqttpublish == 1)):
            if (mqttclient != None):
                mylogs.info("CLEAN UP: Shutdown MQTT")
                mqttclient.on_message = "" #prevent any further message to be proceed
                mqttpublish(1)
                mylogs.info("CLEAN UP: mqtt unsubcribe: " + cfg.mqttsubscribe)
                #Doing it 2 times to be sure we really unsubscribe
                mqttclient.unsubscribe(cfg.mqttsubscribe)
                mqttclient.unsubscribe(cfg.mqttsubscribe)
                mqttclient.disconnect()
                mqttclient.loop_stop()

        sleep(0.5) # wait to be sure that mqtt is really down and no new message will be proceed !
        cfg.ForceBicAlwaysOn = 0 #Prevent BIC will not shutdown
        StartStopOperationCharger(0,1)
        StartStopOperationDisCharger(0,1)

        #CAN close for 0=bic2200 and 1=NPB
        if (mwcandev != None):
            mylogs.info("CLEAN UP: Shutdown MEANWELL DEVICE")
            mylogs.info("Close CAN device")
            mwcandev.can_down()
            mylogs.info("MEANWELL EEPROM COUNTER  NPB:" + str(cfg.MW_NPB_COUNTER) + "  BIC2200: " + str(cfg.MW_BIC_COUNTER))

        if (LT1 != None): #Lumentree
            mylogs.info("CLEAN UP: Shutdown LUMENTREE DEVICE(s)")
            LT1.lt232_close()
            if(LT2 != None): LT2.lt232_close()
            if(LT3 != None): LT3.lt232_close()

        if (jk != None):
            mylogs.info("CLEAN UP: Shutdown JKBMS")
            jk.jkbms_close()

        if (cfg.Selected_LCD == 1):
            printlcd(line1="SCRIPT STOP", line2="REASON UNKNOWN")
            #display.lcd_clear()
            mylogs.info("CLEAN UP: Shutdown LCD/OLED")

        cfg.EstBatteryWh = round(status.EstBatteryWh)
        cfg.iniwrite()

    except Exception as e:
            mylogs.error("ON EXIT EXCEPTION !")
            mylogs.error(str(e))
            cfg.iniwrite()


def handle_exit(signum, frame):
    mylogs.info("SIGNAL TO STOP RECEIVED " + str(signum))
    #sys.exit(0)
    raise(SystemExit)


def CheckPatameter():
    if((cfg.CellvoltageMax > 365) or (cfg.CellvoltageMin < 250)):
        mylogs.error("\n\nCELL VOLTAGE TOO HIGH OR TOO LOW! Voltage: "+ str(cfg.CellvoltageMin) + " - " + cfg.CellvoltageMax + "\n")
        return 1
        
#    if((status.ChargerMainVoltage / cfg.CellCount) != 300):
#        mylogs.error("\n\nCHARGER DOES NOT FIT FOR YOUR BATTERY, TOO LOW/HIGH VOLTAGE !")
#        mylogs.error("Charger Main Voltage: " + str(status.ChargerMainVoltage) + " - CellCount: " + str(cfg.CellCount))
#        return 1

    if((cfg.MW_NPB_COUNTER > 4000000) or (cfg.MW_BIC_COUNTER > 4000000)):
        mylogs.error("\n\nMEANWELL DEVICE EEPROM MAX WRITE REACHED! " + " - NPB: " + str(cfg.MW_NPB_COUNTER) + " - BIC: " + str(cfg.MW_BIC_COUNTER) + "\n")
        return 1
        
    if(cfg.BatteryVoltageSource == 0):
        mylogs.error("\n\nNO VOLTAGE SOURCE DEFINED!\n")
        return 1

    if((cfg.ForceBicAlwaysOn == 1) and ((cfg.Selected_Device_Charger + cfg.Selected_Device_DisCharger) != 0)):
        mylogs.error("YOU CAN ONLY USE ForceBicAlwaysOn WITH BIC2200 CONFIGURED AS CHARGER AND DISCHARGER !")
        mylogs.error("SET ForceBicAlwaysOn to OFF")
        cfg.ForceBicAlwaysOn = 0
        return 0

    #looks good continue
    mylogs.info("Parameter check OK")
    return 0

def MW_EEPROM_Counter_INC(ChargerDisChargemode): #CD = 0: Charger; 1: DisCharger
    mylogs.debug("MW_EEPROM_Counter_INC Mode: " + str(ChargerDisChargemode))
    if(ChargerDisChargemode == 1): #DisCharger only BIC
        cfg.MW_BIC_COUNTER += 1
        mylogs.info("MW_EEPROM_Counter_INC BIC2200: " + str(cfg.MW_BIC_COUNTER))

    if(ChargerDisChargemode == 0): #Charger
        if(cfg.Selected_Device_Charger == 0): #BIC2200
            cfg.MW_BIC_COUNTER += 1
            mylogs.info("MW_EEPROM_Counter_INC BIC2200: " + str(cfg.MW_BIC_COUNTER))
        if(cfg.Selected_Device_Charger == 1): #NPB
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
        
        if (channel == cfg.gpio1):
            mylogs.info("GPIO CALLBACK 1 - Dis/Enable DisCharger")
            #If you use this, the Lumentree must be the DisCharger or lt_foreceoffonstartup must be enabled
            #DisCharger_Lumentree_Set(0,1)
            if(status.DisChargerEnabled==1):
                status.DisChargerEnabled = 0
            else:
                status.DisChargerEnabled = 1
            
        if (channel == cfg.gpio2):
            mylogs.info("GPIO CALLBACK 2 - ReInit CLCD")
            display = i2clcd(cfg.lcdi2cadr)
            display.lcd_clear()
    
        if (channel == cfg.gpio3):
            mylogs.info("GPIO CALLBACK 3 - Nothing to do here")
    
        if (channel == cfg.gpio4):
            mylogs.info("GPIO CALLBACK 3 - Nothing to do here")

    except Exception as e:
            mylogs.error("GPIO CALLBACK EXEPTION !")
            mylogs.error(str(e))
    return

#####################################################################
# Main Status
#####################################################################
def logstatus():
        mylogs.info("-> STATUS: C:" + str(status.ChargerEnabled) + " D:" + str(status.DisChargerEnabled) + " | SOC:" + str(status.BMSSOC) + "%  BattV:" + str(status.BatteryVoltage/100) + "V |  Total: " + str(status.CurrentTotalWatt) + "W  Meter:" + str(status.CurrentWattValue) + "W  Average: " + str(status.CurrentAverageWatt) + "W  LOUT:" + str(status.LastWattValueUsedinDevice) + "W | RCAP: " + str(round(status.EstBatteryWh/1000)) )
        mylogs.info("-> STATUS: BICC: " +  str(cfg.MW_BIC_COUNTER) + " - NPBC: " + str(cfg.MW_NPB_COUNTER))

#####################################################################
# LCD routine
#####################################################################
def printlcd(line1="", line2=""):
    if (cfg.Selected_LCD == 0): return
    try:
        if (line1==""): 
            if(status.LastWattValueUsedinDevice > 0):
                line1 = "PW:" + "{:<5}".format(str(status.CurrentWattValue))  + " O:" + str(status.LastWattValueUsedinDevice)
            else:
                line1 = "PW:" + "{:<5}".format(str(status.CurrentWattValue))  + " I:" + str(status.LastWattValueUsedinDevice)
            
        if (line2==""): line2 = "SC:" + "{:<6}".format(str(status.BMSSOC)+"%") + "C:" + str(status.ChargerEnabled) + " D:" + str(status.DisChargerEnabled)

        
        if (cfg.Selected_LCD == 1):
            display.lcd_clear()
            mylogs.debug("LCD: Print LCD")
            display.lcd_display_string(line1, 1)
            display.lcd_display_string(line2, 2)

    except Exception as e:
            mylogs.error("LCD PRINT EXEPTION !")
            mylogs.error(str(e))
    return

#####################################################################
# MQTT publish
#####################################################################
def mqttpublish(cleanup=0):
    if (cfg.mqttpublish == 0): return
    mylogs.debug("mqtt: publish data to broker")
    try:
        if(cleanup == 1): lwatt = 0
        else: lwatt = status.LastWattValueUsedinDevice
        if(cfg.mqttpublishWATTCut > 0):
            if(abs(lwatt) <= cfg.mqttpublishWATTCut):
                 lwatt = 0
        
        if (cfg.mqttpublishWATT     != ""): mqttclient.publish(cfg.mqttpublishWATT,     payload=lwatt, qos=1, retain=True)
        if (cfg.mqttpublishSOC      != ""): mqttclient.publish(cfg.mqttpublishSOC ,     payload=status.BMSSOC, qos=1, retain=True)
        if (cfg.mqttpublishBatVolt  != ""): mqttclient.publish(cfg.mqttpublishBatVolt , payload=status.BatteryVoltage, qos=1, retain=True)
    except Exception as e:
            mylogs.error("MQTT PUBLISH EXEPTION !")
            mylogs.error(str(e))
    return     

#####################################################################
# BMS Section
#####################################################################
def GetBMSData():
    mylogs.debug("GetBMSData entry:")
    if (cfg.Selected_BMS == 0): #disabled return always full for further checks, you should really use a SOC methode ! 
        status.BMSSOC = 100
        return status.BMSSOC

    #Software BMS, calculate form DC Voltage, not very exact yet ;-)
    #this works only if the EstBh calculation working almost correctly
    if (cfg.Selected_BMS == 1): 
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
        return status.BMSSOC

    #JKBMS reading
    if (cfg.Selected_BMS == 2):
        try:
          ST = jk.jkbms_read()
          mylogs.debug("Cellcount: " + str(jk.cell_count))
          for i in range(jk.cell_count) :
              mylogs.debug("BMS: CellVolt" + str(i) + ": " + str(jk.cells[i]/1000))

          mylogs.debug("BMS: Temp_Fet : " + str(jk.temp_fet))
          mylogs.debug("BMS: Temp_1   : " + str(jk.temp_1))
          mylogs.debug("BMS: temp_2   : " + str(jk.temp_2))
          mylogs.debug("BMS: BatVolt  : " + str(jk.voltage/100))
          mylogs.debug("BMS: Current  : " + str(jk.act_current/100))
          mylogs.debug("BMS: BMSSOC   : " + str(jk.soc))
          status.BMSVoltage = jk.voltage
          status.BMSCurrent = jk.act_current
          status.BMSSOC     = jk.soc 

          BMSstatus.CellCount      = jk.cell_count
          BMSstatus.BMSSOC         = jk.soc
          BMSstatus.BMSCurrent     = jk.act_current
          BMSstatus.BMSVoltage     = jk.voltage
          BMSstatus.BMSTemp_Mosfet = jk.temp_fet
          BMSstatus.BMSTemp1       = jk.temp_1
          BMSstatus.BMSTemp2       = jk.temp_2
          for i in range(BMSstatus.CellCount) :                                                                             
              BMSstatus.BMSCellVoltage[i] = jk.cells[i]                                                                                                    

        except Exception as e:
            mylogs.error("JKBMS READ EXEPTION !")
            mylogs.error(str(e))
            status.BMSSOC = 0

        return status.BMSSOC

    mylogs.error("UNKNOWN BMS USED ! Check Configuration !")
    sys.exit(1)
    return

#####################################################################
#####################################################################
#####################################################################
#Setup Operation mode of charger
def StartStopOperationCharger(val,force=0):
    mylogs.verbose("StartStopOperationCharger entry: " + str(val) + " Force: " + str(force))
    
    if (status.ChargerEnabled == 0):
        val = 0

    if((cfg.ForceBicAlwaysOn == 1) and (status.BICChargeDisChargeMode == 1) and (val == 0) and (force == 0)):
        mylogs.verbose("StartStopOperationCharger: Always on BIC Mode already set to Discharge. Nothing to do here")
        return
    
    #if the Battery is not totally empty anymore, start Discharging
    if((status.BatteryEMPTY == 1) and (status.BatteryVoltage >= cfg.RestartDisChargevoltage)):
        mylogs.info("StartStopOperationCharger: Battery Discharging allowed again. Current Volatge: " + str(status.BatteryVoltage/100) + " (Restart Voltage: " + str(cfg.RestartDisChargevoltage/100) + ")")
        status.BatteryEMPTY = 0

    #if the Battery is not full anymore, start recharging
    if((status.BatteryFULL == 1) and (status.BatteryVoltage <= cfg.RestartChargevoltage)):
        mylogs.info("StartStopOperationCharger: Battery charging allowed again. Current Volatge: " + str(status.BatteryVoltage/100) + " (Restart Voltage: " + str(cfg.RestartChargevoltage/100) + ")")
        status.BatteryFULL = 0

    #Battery is full, stop charing and wait for discharge
    if((status.ChargerStatus  == 1)  and (status.LastChargerGetCurrent <= cfg.StopMinChargeCurrent) and ((status.BatteryVoltage+10) > cfg.FixedChargeVoltage)): # and (status.BMSSOC > 97)): 
        status.BatteryFULL = 1
        force = 2 #force stop charging, 2 if BIC is used with always on
        #Set to est. max of installed battery
        #status.EstBatteryWh = cfg.BatteryTotalWH

    if(status.BatteryFULL == 1):
        mylogs.info("StartStopOperationCharger: Battery Full ! - Charging current too small: " + str(status.LastChargerGetCurrent) + " - Min: " + str(cfg.StopMinChargeCurrent))
        val = 0
    
    if (force==0): #if force = 1, proceeed without any logic 
        if (status.ChargerStatus == 0) and (val == 0): 
            mylogs.verbose("StartStopOperationCharger already off mode")
            return #DisCharger already off, can stop here
    
        #Check if we need to set the new value to the Charger
        p = abs(status.LastWattValueUsedinDevice - val)
    
        if ((val != 0) and (p <= cfg.LastChargePower_delta)):
            mylogs.info("No change to Charger output, Delta is: " + str(p) + "  - Set to :" + str(cfg.LastChargePower_delta))
            return

    if(force==0): 
        SetPowerValArray(cfg.ChargerPowerCalcCount,val)

    if (cfg.Selected_Device_Charger <= 1): #BIC and NPB-abc0
        #try to set the new ChargeCurrent if possible
        Charger_Meanwell_Set(val,force)
        return
    
    if (cfg.Selected_Device_Charger == 255):     #Simulator
        status.LastWattValueUsedinDevice = 0;  #prevent wrong calulation
        mylogs.info("Simulator Charger set to: " + str(val) + "W")
        return     

    mylogs.error("Charger type not supported yet")
    sys.exit(1)
    return


def StartStopOperationDisCharger(val,force=0):
    mylogs.verbose("StartStopOperationDisCharger entry: " + str(val) + " Force: " + str(force))
    
    if (status.DisChargerEnabled == 0):
        mylogs.verbose("StartStopOperationDisCharger: DisCharger disabled !")
        val = 0

    if((cfg.ForceBicAlwaysOn == 1) and (status.BICChargeDisChargeMode == 0) and (val == 0) and (force == 0)):
        mylogs.verbose("StartStopOperationDisCharger: Always on BIC Mode already set to Charge. Nothing to do here")
        return

    #if the Battery is not full anymore, start recharging
    if((status.BatteryFULL == 1) and (status.BatteryVoltage <= cfg.RestartChargevoltage)):
        mylogs.info("StartStopOperationDisCharger: Battery charging allowed again. Current Volatge: " + str(status.BatteryVoltage/100) + " (Restart Voltage: " + str(cfg.RestartChargevoltage/100) + ")")
        #BatterFullSpecialOperation(0)
        status.BatteryFULL = 0

    #if the Battery is not totally empty anymore, start Discharging
    if((status.BatteryEMPTY == 1) and (status.BatteryVoltage >= cfg.RestartDisChargevoltage) and (status.BMSSOC >=cfg.BMSRestartSOC)):
        mylogs.info("StartStopOperationDisCharger: Battery Discharging allowed again. Current Volatge: " + str(status.BatteryVoltage/100) + " (Restart Voltage: " + str(cfg.RestartDisChargevoltage/100) + ")")
        status.BatteryEMPTY = 0

    #Battery is empty, stop Discharing and wait for charging
    # Do not discharge any further if SOC or voltage is lower than specified
    if(((status.BatteryVoltage > 0) and (status.BatteryVoltage <= cfg.StopDischargeVoltage)) or (status.BMSSOC <= cfg.BMSminSOC) ):
        status.BatteryEMPTY = 1
        #Set EstBatteryWh to 0, because for this schript the Battery is empty 
        status.EstBatteryWh = 0

    if(status.BatteryEMPTY == 1):
        mylogs.info("StartStopOperationDisCharger: Battery EMPTY ! Battery Voltage: " + str(status.BatteryVoltage/100) + ' - SOC: ' + str(status.BMSSOC))
        val = 0

    #Check if Battery Volatge is online, if not try to disable discharger
    if(status.BatteryVoltage == 0):
        mylogs.error("StartStopOperationDisCharger: Battery Voltage can not be read. Battery Voltage: 0")
        val = 0

    if (force==0): #if force = 1, proceeed without any logic 

        if((status.DisChargerStatus == 0) and (val == 0)): 
            mylogs.verbose("StartStopOperationDisCharger: Already off mode")
            return #DisCharger already off, can stop here
        

        #Check if we need to set the new value to the DisCharger
        p = abs((status.LastWattValueUsedinDevice + status.ZeroExportWatt) - val)
        
        if ((val != 0) and (p <= cfg.LastDisChargePower_delta)): #0:must be processed
            mylogs.info("No change to DisCharger. Delta is: " + str(p) + " (of: " + str(cfg.LastDisChargePower_delta) + ") - Last Value: " + str(status.LastWattValueUsedinDevice) + " (ZeroExport: " + str(cfg.ZeroDeltaDisChargeWATT) + ") - New: " + str(val))
            #status.actchargercounter = 1 #Reset counter to 1
            return

    Newval = val      #used for calculation
    status.ZeroExportWatt = 0
    if (cfg.ZeroDeltaDisChargeWATT > 0):
        if (val > cfg.ZeroDeltaDisChargeWATT):
            Newval = val - cfg.ZeroDeltaDisChargeWATT
            status.ZeroExportWatt = cfg.ZeroDeltaDisChargeWATT
            mylogs.info("ZEROExport: Meter: " + str(val) + " -> ZeroWatt: " + str(Newval) + " (Delta: " + str(cfg.ZeroDeltaDisChargeWATT) + ")")

    if(force==0): 
        SetPowerValArray(cfg.DisChargerPowerCalcCount,val)

    #Which Device used
    mylogs.debug("StartStopOperationDisCharger: " + str(Newval))
    if (cfg.Selected_Device_DisCharger == 0): #Meanwell BIC-2200
        DisCharger_BIC2200_Set(Newval,force)
        return     

    if (cfg.Selected_Device_DisCharger == 1): #Lumentree
        DisCharger_Lumentree_Set(Newval,force)    
        return     
    
    if (cfg.Selected_Device_DisCharger == 255): #Simulator
        mylogs.info("Simulator DisCharger set to: " + str(Newval) + "W")
        status.LastWattValueUsedinDevice = 0; #prevent wrong calulation
        return     

    mylogs.warning("DisCharger type not supported yet")
    return


#####################################################################
#####################################################################
#####################################################################
# Operation Meanwell
def StartStopOperationMeanwell(val, CD, force=0):
    try:
        mylogs.verbose("StartStopOperationMeanwell entry - value: " + str(val) + " Force: " + str(force))
        #read current status from device
        
        opmode = mwcandev.operation(0,0)
        if((cfg.ForceBicAlwaysOn==1) and (opmode==1) and ((force==0) or (force==2))): #force=2 is for BIC always on if battary full
            return 1
        
        mylogs.debug("Meanwell: Operation mode: " + str(opmode))
        if (val == 0): #set to off  
            if((opmode != 0) or (force==1)):
                mwcandev.operation(1,0)
                mylogs.verbose("Meanwell: Operation mode set to: OFF")
                MW_EEPROM_Counter_INC(CD)
                sleep(0.3)
            else:
                mylogs.verbose("Meanwell: Operation mode already OFF")
        else:
            if((opmode != 1) or (force==1)):
                mwcandev.operation(1,1)   
                mylogs.verbose("Meanwell: Operation mode set to: ON")
                MW_EEPROM_Counter_INC(CD)
                sleep(0.3)
            else:
                mylogs.verbose("Meanwell: Operation mode already ON")

    except Exception as e:
        mylogs.error("StartStopOperationMeanwell: EXEPTION !")
        mylogs.error(str(e))
        mwcandev.can0.flush_tx_buffer() #flush buffer to clear message queue
   
    return val


def Charger_Meanwell_Set(val,force=0):
    try:
        if(mwcandev == None): 
            mylogs.error("Charger_Meanwell_Set mwcandev not exists")
            return

        mylogs.verbose("Charger_Meanwell_Set entry - value: " + str(val) + " Force: " + str(force))

        #For BIC set Charge mode first
        if cfg.Selected_Device_Charger == 0: #BIC2200
            status.BICChargeDisChargeMode = mwcandev.BIC_chargemode(0,0)
            if(status.BICChargeDisChargeMode==1):
                mylogs.info("Charger_Meanwell_Set: Set BIC2200 to Charge Mode")
                mwcandev.BIC_chargemode(1,0)  #set BIC to Chargemode
                sleep(0.3)
                status.BICChargeDisChargeMode = mwcandev.BIC_chargemode(0,0)
                MW_EEPROM_Counter_INC(0)

        #read voltage and current from NBB device
        vout  = mwcandev.v_out_read()
        status.ChargerVoltage = vout 
        
        #Calculate current for meanwell + or - to the actual power from PV / Grid
        #*-10000 --> Vout and iout value is *100 --> 2x100 = 10000
        #charging/discharging current in *100 for meanwell --> e.g. 2600 = 26A
        
        Current    = (val * -10000) / vout 
        IntCurrent = int(Current)
        
        if (IntCurrent >= cfg.MaxChargeCurrent):
            IntCurrent = cfg.MaxChargeCurrent 

        #NPB device has a minimal charge current
        #Stop if this value is reached or allow take power from grid to charge 
        if (IntCurrent <= cfg.MinChargeCurrent):
            #calculate ZeroDelta if configured
            ZeroDelta = int((cfg.ZeroDeltaChargerWatt / vout)*10000)
            status.ZeroImportWatt = 0 #Reset to 0 and see if we need it later

            if (IntCurrent < (cfg.MinChargeCurrent - ZeroDelta)):
                mylogs.info("Charger_Meanwell_Set: Current too small - " + str(IntCurrent) + " - MinCurrent: " + str(cfg.MinChargeCurrent) + " - ZeroDelta: " + str(ZeroDelta) + " = " + str(IntCurrent+ZeroDelta) + " -> Device OFF")
                IntCurrent = 0;
                OPStart = False 
            else:
                IntCurrent = cfg.MinChargeCurrent
                status.ZeroImportWatt = int((cfg.MinChargeCurrent - ZeroDelta)*vout/10000)
                mylogs.info("Charger_Meanwell_Set: ZeroImportWatt used - allow from GRID: " + str(status.ZeroImportWatt))

        if (IntCurrent != status.LastChargerSetCurrent):
            if ((status.actchargercounter >= cfg.MeterUpdateChargeCounter) or (force==1)):
                mylogs.info("Charger_Meanwell_Set: >>>> Set new current to: " + str(IntCurrent) + "  (Last current set: " + str(status.LastChargerSetCurrent) + ") <<<<")
                
                if(IntCurrent == 0):
                    #Probably no need to set since device will be set to OFF mode
                    if(cfg.ForceBicAlwaysOn == 1): #only for BIC in always on mode
                        mylogs.info("Charger_Meanwell_Set: BIC-2200 SET IntCurrent = 0")
                        c = mwcandev.i_out_set(1,IntCurrent)
                        MW_EEPROM_Counter_INC(0)
                        sleep(0.4)
                    else:
                        mylogs.info("Charger_Meanwell_Set: IntCurrent = 0 - Do not set -> Device will be set to OFF")
                        
                    status.LastChargerSetCurrent = IntCurrent;
                    OPStart = False #device start
                else:
                    if((status.LastChargerGetCurrent < (status.LastChargerSetCurrent-50)) and (status.BMSSOC > 97)):
                        mylogs.info("Charger_Meanwell_Set: >>>> NO SET -> BATTERY ALMOST FULL: " + str(IntCurrent) + " (Last current GET: " + str(status.LastChargerGetCurrent)  + " ->  Last current SET: " + str(status.LastChargerSetCurrent) + " <<<<")
                        OPStart = True #device start or continue
                    else:
                        mylogs.info("Charger_Meanwell_Set: SET NEW CURRENT TO: " + str(IntCurrent))
                        c = mwcandev.i_out_set(1,IntCurrent)
                        status.LastChargerSetCurrent = IntCurrent;
                        MW_EEPROM_Counter_INC(0)
                        OPStart = True #device start or continue
                        sleep(0.4)
                        
                status.actchargercounter = 1 #Reset counter to 1
            else:
                mylogs.verbose("Charger_Meanwell_Set: Wait for next change: " + str(status.actchargercounter) + "  of: " + str(cfg.MeterUpdateChargeCounter))
                status.actchargercounter += 1
                if(status.ChargerStatus == 0):#do not change the current status
                    OPStart = False
                else:
                    OPStart = True             
        else:
            if(IntCurrent != 0):
                mylogs.verbose("Charger_Meanwell_Set: No New current to set. Last current: " + str(status.LastChargerSetCurrent))
                OPStart = True #device start or continue
            
                
    #    if(OPStart):
    #        status.ChargerStatus  = 1
    #    else:
    #        status.ChargerStatus  = 0
    #        status.ZeroImportWatt = 0
        

        #IF Bic uses always on OPstart True
        if((cfg.ForceBicAlwaysOn == 1) and (force != 1)): OPStart = True

        #try to set the new ChargeCurrent if possible
        if (OPStart == True): #if true start mw device 
            mylogs.verbose("Charger_Meanwell_Set: OPSTART TRUE : Start Meanwell Device")
            status.ChargerStatus  = 1
            StartStopOperationMeanwell(1,0,force)
        else: 
            mylogs.verbose("OPSTART FALSE: Stop Meanwell Device")
            status.ChargerStatus  = 0
            status.ZeroImportWatt = 0
            StartStopOperationMeanwell(0,0,force)     

        #wait to read the current after MW starts to get a value != 0
        #if 0 returns Battery is full, checked in StartStopCharger
        sleep(0.2)
        status.LastChargerGetCurrent  = mwcandev.i_out_read()
        NewVal = int((status.LastChargerGetCurrent*vout)/10000)
        mylogs.info("Charger_Meanwell_Set: BVout:" + str(vout/100) + ":V: Iout:" + str(status.LastChargerGetCurrent/100) + ":A: ICalc:" + str(IntCurrent/100) + ":A: ILastSet:" + str(status.LastChargerSetCurrent/100) + ":A - GET ACT: " + str(NewVal) + "W  (C:" + str(status.actchargercounter) + "-" + str(cfg.MeterUpdateChargeCounter) + ")")
        status.LastWattValueUsedinDevice = NewVal*(-1)

    except Exception as e:
        mylogs.error("Charger_Meanwell_Set: EXEPTION !")
        mylogs.error(str(e))
        mwcandev.can0.flush_tx_buffer() #flush buffer to clear message queue

    return OPStart

#####################################################################
# Operation BIC-2200 DisCharger Meanwell
def DisCharger_BIC2200_Set(val,force=0):
    try:
        if(mwcandev == None): 
            mylogs.error("DisCharger_BIC2200_Set mwcandev not exists")
            return

        mylogs.verbose("DisCharger_BIC2200_Set entry - value: " + str(val) + " Force: " + str(force))

        #Check Mode to prevent to set it again if not needed
        #0=Charger; 1=DisCharger
        status.BICChargeDisChargeMode = mwcandev.BIC_chargemode(0,0)
        if(status.BICChargeDisChargeMode==0):
            mylogs.info("StartStopOperationDisCharger: Set BIC2200 to DisCharge Mode")
            mwcandev.BIC_chargemode(1,1)  #set BIC to DisChargemode
            sleep(0.3)
            status.BICChargeDisChargeMode = mwcandev.BIC_chargemode(0,0)
            MW_EEPROM_Counter_INC(1)

        #read voltage from BIC device
        vout  = mwcandev.v_out_read()
        
        #Calculate current for meanwell + or - to the actual power from PV / Grid
        #*-10000 --> Vout and iout value is *100 --> 2x100 = 10000
        #charging/discharging current in *100 for meanwell --> e.g. 2600 = 26A
        
        Current = (val * 10000) / vout; 

        IntCurrent = int(Current)
        OPStart = True #device start

        if (IntCurrent >= cfg.MaxDisChargeCurrent):
            IntCurrent = cfg.MaxDisChargeCurrent 

    #    #calculate ZeroDelta if configured
        ZeroDelta = int((cfg.ZeroDeltaDisChargeWATT / vout)*10000)
        mylogs.verbose("ZERODELTA IS: " + str(ZeroDelta))
        status.ZeroExportWatt = 0 #Reset to 0 and see if we need it later

        #BIC device has a minimal DisCharge current
        #Stop if this value is reached or allow take power from grid to charge 
        if (IntCurrent <= cfg.MinDisChargeCurrent):
            if (IntCurrent < (cfg.MinDisChargeCurrent - ZeroDelta)):
                if(cfg.ForceBicAlwaysOn == 1): #BIC set to Min
                    IntCurrent = cfg.MinDisChargeCurrent
                    mylogs.info("Meanwell BIC: Current too small - " + str(IntCurrent) + " - MinCurrent: " + str(cfg.MinDisChargeCurrent) + " - ZeroDelta: " + str(ZeroDelta)+ " -> Always ON")
                    OPStart = True
                else:
                    IntCurrent = 0;
                    mylogs.info("Meanwell BIC: Current too small - " + str(IntCurrent) + " - MinCurrent: " + str(cfg.MinDisChargeCurrent) + " - ZeroDelta: " + str(ZeroDelta)+ " -> Device OFF")
                    OPStart = False 
            else:
                IntCurrent = cfg.MinDisChargeCurrent
                status.ZeroImportWatt = cfg.ZeroDeltaChargerWatt
                mylogs.info("Meanwell BIC: ZeroExportWatt used - " + str(cfg.ZeroDeltaDisChargeWATT))

        if (IntCurrent != status.LastDisChargerCurrent):
            if ((status.actchargercounter >= cfg.MeterUpdateDisChargeCounter) or (force==1)):
                mylogs.info("Meanwell BIC: Set new current to: " + str(IntCurrent) + "  (Last current: " + str(status.LastDisChargerCurrent) + ")")
                c = mwcandev.BIC_discharge_i(1,IntCurrent)
                status.LastDisChargerCurrent = IntCurrent;
                MW_EEPROM_Counter_INC(1)
                status.actchargercounter = 1 #Reset counter to 1 
                sleep(0.4) #wait for next read
            else:
                mylogs.info("Meanwell BIC: Wait for next change: " + str(status.actchargercounter) + "  of: " + str(cfg.MeterUpdateDisChargeCounter))
                status.actchargercounter += 1

        else:
            mylogs.info("Meanwell BIC: No new DisCharge current to set. Last current: " + str(status.LastDisChargerCurrent))
            
        
        #try to set the new ChargeCurrent if possible
        if (OPStart == True): #if true start mw device 
            mylogs.verbose("OPSTART TRUE : Start BIC2200")
            status.DisChargerStatus  = 1
            StartStopOperationMeanwell(1,1,force)
        else: 
            mylogs.verbose("OPSTART FALSE: Stop BIC2200")
            status.DisChargerStatus  = 0
    #        status.ZeroExportWatt = 0
            StartStopOperationMeanwell(0,1,force)     

        sleep(0.2)
        iout  = mwcandev.i_out_read()
        NewVal = int((iout*vout)/-10000)

        mylogs.info("Meanwell BIC: W Battery_Vout:" + str(vout/100) + ":V: Battery_I_out:" + str(iout/100) + ":A: I Calc:" + str(IntCurrent) + " = " + str(IntCurrent/100) + ":A --> WATT: " + str(NewVal))

        status.LastWattValueUsedinDevice = NewVal

    except Exception as e:
        mylogs.error("DisCharger_BIC2200_Set: EXEPTION !")
        mylogs.error(str(e))
        mwcandev.can0.flush_tx_buffer() #flush buffer to clear message queue
    
    return


#####################################################################
#####################################################################
#####################################################################
# Operation Lumentree reopen if Device has communication errors
def Lumentree_ReOpen():
    mylogs.warning("Lumentree_ReOpen !")
    
    try:
        LT1.lt232_close()
        if (cfg.lt_count > 1): LT2.lt232_close()
        if (cfg.lt_count > 2): LT3.lt232_close()
        sleep(0.4)
        
        LT1.lt232_open()
        if (cfg.lt_count > 1): LT2.lt232_open()
        if (cfg.lt_count > 2): LT3.lt232_open()

    except Exception as e:
        mylogs.error("LUMENTREE REOPEN FAILED !")
        mylogs.error(str(e))
    return    

#####################################################################
# Check periodically if Lumentree is still online. If not try to reopen
def Lumentree_Check():
    if (cfg.Selected_Device_DisCharger != 1): return

    mylogs.verbose("------> Lumentree Check Alive ...")
    try:
        status.DisChargerVoltage = LT1.readDCvoltage() * 10  #return 3 digits, need 4 for compare --> *10
        sleep(0.1)
        status.LT1_Temperature = int(LT1.readtemp()) #for temperature test
        if (cfg.lt_count > 1): status.LT2_Temperature = int(LT2.readtemp()) #for temperature test
        if (cfg.lt_count > 2): status.LT3_Temperature = int(LT3.readtemp()) #for temperature test
        mylogs.debug("------> Lumentree Check Alive OK. BattVoltage: " + str(status.DisChargerVoltage)) # + " - Temperature: L1:" + str(status.LT1_Temperature) + " L2:" + str(status.LT2_Temperature) + " L3:" + str(status.LT3_Temperature))
        return 1

    except Exception as e:
        mylogs.error("------> LUMENTREE CHECK ALIVE EXEPTION !")
        mylogs.error(str(e))
        status.LastWattValueUsedinDevice = 10 #
        status.DisChargerStatus = 1           #try again every time a new Power value is received 
        return 0


#####################################################################
# Operation Lumentree Sun600/1000/2000
def DisCharger_Lumentree_Set(val,force=0):
    mylogs.verbose("DisCharger_Lumentree_Set entry - value: " + str(val))

    if (cfg.MaxDisChargeWATT <= val):
        outpower = cfg.MaxDisChargeWATT
    else:
        if (cfg.MinDisChargeWATT >= val):
            outpower = 0     #Stop DisCharger, too low Watt needed
        else:
            outpower = val
    
    if (val==0): outpower = 0
    
    if (force==0):
        if((status.LastWattValueUsedinDevice == 0) and (status.DisChargerStatus == 1)):
            #Lumentree has not raised the output, but we get 0 already to set off again
            p = 10
        else:
            p = abs(status.LastWattValueUsedinDevice - outpower)

        if(p <= 8): #since Lumentree don't have exact value we can set, use +/-8 to test if we have the same value
            mylogs.verbose("DisCharger_Lumentree_Set: No change to DISCharger output: " + str(status.LastWattValueUsedinDevice) + " NewWatt Value: " + str(outpower))
            return 0     #no need to set the same again, mainly for max power, delta is handled above
        else:
            mylogs.verbose("DisCharger_Lumentree_Set: LastWATT value: " + str(status.LastWattValueUsedinDevice) + " NewWatt Value: " + str(outpower))
    
        #only needs to read one LT for DC voltage, all should be connected to the same battery
        try:
            DCvoltage = 100    #for force to goto set watt output if LT reconnect
            DCvoltage = LT1.readDCvoltage()
        except Exception as e:
            mylogs.error("LUMMENTREE SET EXEPTION READ DC VOLTAGE!")
            mylogs.error(str(e))
        
        if (DCvoltage < 10): 
            if (status.DisChargerStatus == 0):
                #only if DisCarger is set already to OFF, otherwise proceed to power off
                mylogs.info("DisCharger_Lumentree_Set: DC volatge too low. Probably Battery empty or defect : " + str(DCvoltage))
                return
            else:
                #Disable DisCharger
                outpower = 0

    sleep(0.1)  #wait 0.1 seconds to read next value

    #calculate the power for each Lumentree
    
    if (outpower <= cfg.lt1_maxwatt):
        outpower1 = outpower
    else:
        outpower1 = cfg.lt1_maxwatt
    outpower  = outpower - outpower1
        
    if (outpower <= cfg.lt2_maxwatt):
        outpower2 = outpower
    else:
        outpower2 = cfg.lt2_maxwatt
    outpower  = outpower - outpower2

    if (outpower <= cfg.lt3_maxwatt):
        outpower3 = outpower
    else:
        outpower3 = cfg.lt3_maxwatt
    outpower  = outpower - outpower3
    
    mylogs.info("DisCharger_Lumentree_Set : Outpower set to LT1: " + str(outpower1) + "   LT2: " + str(outpower2) + "   LT3: " + str(outpower3))
    if (outpower != 0):
        mylogs.info("DisCharger_Lumentree_Set : Outpower should be 0 now - check settings ! - " + str(outpower))
        
    try:
        #Lumentree Inverter 1
        mylogs.verbose("DisCharger_Lumentree_Set   (1) : " + str(outpower1))
        LT1.set_watt_out(outpower1);
        sleep(0.2)  #wait 0.2 seconds to write next value
        status.LastWattValueUsedinDevice = LT1.read_watt_out()
    
        #Lumentree Inverter 2
        if (cfg.lt_count > 1):
            mylogs.verbose("DisCharger_Lumentree_Set   (2) : " + str(outpower2))
            LT2.set_watt_out(outpower2);
            sleep(0.2)  #wait 0.2 seconds to write next value
            status.LastWattValueUsedinDevice = status.LastWattValueUsedinDevice + LT2.read_watt_out()
            
        #Lumentree Inverter 3
        if (cfg.lt_count > 2):
            mylogs.verbose("DisCharger_Lumentree_Set   (3) : " + str(outpower3))
            LT3.set_watt_out(outpower3);
            sleep(0.2)  #wait 0.2 seconds to write next value
            status.LastWattValueUsedinDevice = status.LastWattValueUsedinDevice + LT3.read_watt_out()


        #Lumentree return sometime > 1 if set to zero
        #if(status.LastWattValueUsedinDevice <= 3): status.LastWattValueUsedinDevice = 0

        #This must be set lastest possible to check Status in other functions
        #Since Lumentree needs some time to set the output, wait until LT1.read_watt_out really is 0.
        if ((val == 0) and (status.LastWattValueUsedinDevice == 0)): 
            status.DisChargerStatus = 0
        else:
            status.DisChargerStatus = 1

    except Exception as e:
        mylogs.error("LUMMENTREE SET EXEPTION !")
        mylogs.error(str(e))
        status.LastWattValueUsedinDevice = 10 #force to go here
        status.DisChargerStatus = 1           #prevent not setting off, if LT is back again 
        Lumentree_ReOpen()

    mylogs.info("DisCharger_Lumentree_Set read Total: " + str(status.LastWattValueUsedinDevice))
    return 


def GetChargerVoltage():
    mylogs.debug("GetChargerVoltage ...")
    try:
        if (cfg.Selected_Device_Charger <= 1): #BIC and NPB-abc0
            status.ChargerVoltage = mwcandev.v_out_read()

    except Exception as e:
        mwcandev.can0.flush_tx_buffer() #flush buffer to clear message queue
        mylogs.error("GetChargerVoltage EXEPTION !")
        mylogs.error(str(e))
    return status.ChargerVoltage


def GetDisChargerVoltage():
    mylogs.debug("GetDisChargerVoltage ...")
    try:
        if (cfg.Selected_Device_DisCharger == 0): #BIC2200
            status.DisChargerVoltage = mwcandev.v_out_read()

        if (cfg.Selected_Device_DisCharger == 1): #Lumentree
            #status.DisChargerVoltage = LT1.readDCvoltage() * 10 #return 3 digits, need 4 for compare --> *10
            mylogs.debug("GetDisChargerVoltage: Nothing to do here, this is already done in Lumentree_Check !")

    except Exception as e:
        mwcandev.can0.flush_tx_buffer() #flush buffer to clear message queue
        mylogs.error("GetDisChargerVoltage EXEPTION !")
        mylogs.error(str(e))
    return status.ChargerVoltage


def GetBatteryVoltage():
    mylogs.debug("GetBatteryVoltage ...")
    try:
        if(cfg.BatteryVoltageSource == 0):
            status.BatteryVoltage = cfg.FixedChargeVoltage #do not use it, assume always full

        if(cfg.BatteryVoltageSource == 1):
            status.BatteryVoltage = status.BMSVoltage

        if(cfg.BatteryVoltageSource == 2):
            GetChargerVoltage()
            status.BatteryVoltage = status.ChargerVoltage

        if(cfg.BatteryVoltageSource == 3):
            GetDisChargerVoltage()
            status.BatteryVoltage = status.DisChargerVoltage

        #add the voltage correction to the value + or -
        status.BatteryVoltage = status.BatteryVoltage + cfg.BatteryVoltageCorrection

    except Exception as e:
        mylogs.error("GetBatteryVoltage EXEPTION !")
        mylogs.error(str(e))

    return

def CheckTemperatures():
    mylogs.debug("CheckTemps ...")
    try:
        if(cfg.Selected_Device_Charger == 0):
            status.MW_BIC_Temperature = int(mwcandev.temp_read()/10) #need only 2 digits
        if(cfg.Selected_Device_Charger == 1):
            status.MW_NPB_Temperature = int(mwcandev.temp_read()/10) #need only 2 digits

        if(status.LT1_Temperature > cfg.lt_MaxTemp):
            mylogs.error("CheckTemperatures: LT1 Temperature too high")
        if(status.LT2_Temperature > cfg.lt_MaxTemp):
            mylogs.error("CheckTemperatures: LT2 Temperature too high")
        if(status.LT3_Temperature > cfg.lt_MaxTemp):
            mylogs.error("CheckTemperatures: LT3 Temperature too high")
        if(BMSstatus.BMSTemp_Mosfet > cfg.BMS_MaxTempMosFet):
            mylogs.error("CheckTemperatures: BMSTemp_Mosfet Temperature too high")
        if(BMSstatus.BMSTemp1 > cfg.BMS_MaxTemp1):
            mylogs.error("CheckTemperatures: BMSTemp1 Temperature too high")
        if(BMSstatus.BMSTemp2 > cfg.BMS_MaxTemp2):
            mylogs.error("CheckTemperatures: BMSTemp2 Temperature too high")
        if(status.MW_NPB_Temperature > cfg.MW_NPB_MaxTemp):
            mylogs.error("CheckTemperatures: MW_NPB_Temperature Temperature too high")
        if(status.MW_BIC_Temperature > cfg.MW_BIC2200_MaxTemp):
            mylogs.error("CheckTemperatures: MW_BIC_Temperature Temperature too high")

        mylogs.verbose("CheckTemperatures: MWBIC: " + str(status.MW_BIC_Temperature) + " MWNPB: " + str(status.MW_NPB_Temperature) + \
                       " LT1: " + str(status.LT1_Temperature) + " LT2: " + str(status.LT2_Temperature) + " LT3: " + str(status.LT3_Temperature) + \
                       " BMSFET: " + str(BMSstatus.BMSTemp_Mosfet) + " BMST1: " + str(BMSstatus.BMSTemp1) + " BMST2: " + str(BMSstatus.BMSTemp2))

    except Exception as e:
        mylogs.error("CalcBatteryWh EXEPTION !")
        mylogs.error(str(e))

    return

def CalcBatteryWh():
    mylogs.debug("CalcBatteryWh ...")
    try:
        if(status.LastWattValueUsedinDevice <= 0):
            EF = 1 #Charger do not need a correction, we read the output of the charger
        else:
            EF = status.DisCharger_efficacy_factor

        now  = datetime.datetime.now()
        diff = (now - status.LastMeterTime).total_seconds()
        #get the millWattHour in seconds of the LastWattValueUsedinDevice
        #-1000: we get negative value for charging, convert to positive values
        #DisCharger_efficacy_factor needed because we need more current than we request WATT of the DisCharger
        LastWatt_mWh = status.LastWattValueUsedinDevice * EF * -1000 / 3600

        #and multiply with the duration
        Bat_mWh = LastWatt_mWh * diff
        status.EstBatteryWh = status.EstBatteryWh + Bat_mWh
        status.LastMeterTime = now
        mylogs.verbose("CalcBatteryWh: LastWatt_mWh :" + str(round(LastWatt_mWh,2)) + " - Bat_mAH: " + str(round(Bat_mWh,2)) + " - EF: " + str(EF) + " - TimeDiff: " + str(round(diff,2)))

    except Exception as e:
        mylogs.error("CalcBatteryWh EXEPTION !")
        mylogs.error(str(e))

#####################################################################
#calculate the output power by array
#####################################################################
def SetPowerValArray(CDlength,Val):
    try:
        if(CDlength == status.powercalccount):
            return

        mylogs.info("SetPowerValArray CurrentLength: " + str(status.powercalccount) + "  NewLength: " + str(CDlength) + " Value: " + str(Val))
        #The new arraylength is smaller, just
        if(CDlength < status.powercalccount):
            status.powercalccount = CDlength

        #New length is greater than old one, just fill the array with the current value
        if(CDlength > status.powercalccount):
            status.powercalccount = CDlength
            for x in range(max(1,status.powercalccount)): 
                powervalarray[x] = Val

    except Exception as e:
        mylogs.error("SetPowerValArray EXEPTION !")
        mylogs.error(str(e))

    return

def getoutputpower(val):
    mylogs.debug("getoutputpower entry ...")

    try:
        status.ProcessCount+=1
        if(status.ProcessCount > 20): #every 20 power value reads, if set to 2 seconds --> all 40 seconds 
            status.ProcessCount = 1
            status.WebRebootSDcounter = 0 #reset rebootcounter for webinterface

            GetBMSData()  #Read all data and set some status IDs
            Lumentree_Check()  #Check every minute if LT is online, and get CD Voltage, if not try to reconnect
            GetBatteryVoltage()
            CheckTemperatures()

        #check the total Watt,
        status.CurrentWattValue = val;
        status.CurrentTotalWatt = status.CurrentWattValue + status.LastWattValueUsedinDevice

        mylogs.debug("getoutputpower: CurrentTotalWatt         : " + str(status.CurrentTotalWatt))
        mylogs.debug("getoutputpower: LastWattValueusedinDevice: " + str(status.LastWattValueUsedinDevice))
        #add new value to array
        status.LastPowerArrayPosition += 1
        if (status.LastPowerArrayPosition >= status.powercalccount):
             status.LastPowerArrayPosition = 0
        powervalarray[status.LastPowerArrayPosition] = status.CurrentTotalWatt
        #get average value of array
        r = round(sum(powervalarray[0:status.powercalccount]) / status.powercalccount)
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
#Setup Charge / Discharge here depending of Power
#power negative = from PV ; power positive = from Grid
def process_power(power):
    try:
        mylogs.debug("process_power entry: " + str(power))

        now  = datetime.datetime.now()
        diff = (now - status.LastMeterTime).total_seconds()
        #status.LastMeterTime will be set in CalcBatteryWh
        if(diff < 1.45): #2 seconds minmum, we need up to  550ms for processing
            mylogs.warning("process_power: Too fast power meter reading ! Ignore value: " + str(diff))
            return

        NewPower = getoutputpower(power)

        OPStart = False #should the device do something
        mylogs.verbose("TotalWatt: " + str(power) + "W  -  CalcAverage: " + str(status.CurrentAverageWatt) + "W")

#######################################################################################################################################
#######  Method 0 DEBUG ###############################################################################################################
#######################################################################################################################################
        if (cfg.PowerControlmethod == 0):
            mylogs.error("PowerControlmethod: 0 - DO NOT USE - ONLY FOR DEBUG")

#######################################################################################################################################
#######  Method 1 Universal, Just check if positive or negative power #################################################################
#######################################################################################################################################
        if (cfg.PowerControlmethod == 1):
            mylogs.debug("PowerControlmethod: 1 - Universal mode")

            if (status.ZeroImportWatt > 0):      #charger aviod to take from Grid for charging, check if still valid
                if((NewPower + status.ZeroImportWatt) > cfg.ZeroDeltaChargerWatt):
                    status.ZeroImportWatt = 0   #too much delta, reset and use normal way
                else:
                    mylogs.verbose("ChargeMethod: 1 with ZeroImport")
                    StartStopOperationCharger(NewPower)
                    return power

            # Charge / Discharge calculation
            # charge, getting power from PV, charge battery now 
            if(NewPower < 0):
                mylogs.debug("ChargeMethod: 1")
                StartStopOperationDisCharger(0) #stop Discharging
                StartStopOperationCharger(NewPower)
                return power

            # discharge, getting power from Battery to house
            if (NewPower >= 0): 
                mylogs.debug("DisChargeMethod: 1")
                StartStopOperationCharger(0) #stop charging 
                StartStopOperationDisCharger(NewPower)
                return power

#######################################################################################################################################
# Method 2...
#######################################################################################################################################
#       if (cfg.PowerControlmethod == 2):
#            print("Method 2")


#######################################################################################################################################
#######  Method 255 Simulator #########################################################################################################
#######################################################################################################################################
        if (cfg.PowerControlmethod == 255):
            mylogs.debug("PowerControlmethod 255 - Simulator")
            if (power > 0):
                StartStopOperationCharger(0)
                StartStopOperationDisCharger(NewPower)
            else:
                StartStopOperationCharger(NewPower)
                StartStopOperationDisCharger(0)    
            return power

    except Exception as e:
        mylogs.error("process_power EXEPTION !")
        mylogs.error(str(e))

    return power #as fallback

#######################################################################################################################################
#######################################################################################################################################
#######################################################################################################################################
#######  Get Power function ###########################################################################################################
#######################################################################################################################################

#####################################################################
# http request
def http_request():
    #--------- Read Power Meter via http
    try:
        power = METER.GetPowermeterWatts()
        mylogs.verbose("http: Power message: " + str(power))
        
    except Exception as e:
        mylogs.error("HTTP CONNECTION ERROR")
        mylogs.error(str(e))
        #Stop Operation if setting set
        if(cfg.StopOnConnectionLost==1):
            StartStopOperationCharger(0,1)
            StartStopOperationDisCharger(0,1)
        return
            
    process_power(power)
    return

#####################################################################
# Simulator request, just a random number
def simulator_request():
    #--------- Create a random power value
    
    power = random.randrange(-500, 500, 10)        
    process_power(power)

#####################################################################
#####################################################################
# mqtt functions
def mqtt_on_connect(client, userdata, flags, rc):
    mylogs.info("mqtt: Connected with mqttserver")
    #Subscribe for actual Power from mqtt server
    if (cfg.GetPowerOption==0):
        mylogs.info("mqtt: Subscribe for toipc " + cfg.mqttsubscribe)
        mqttclient.subscribe(cfg.mqttsubscribe,qos=2)
    return

def mqtt_on_disconnect(client, userdata, rc):
    mylogs.warning("mqtt: DISConnected from mqttserver")
    mylogs.warning("mqtt: " + str(client))
    if rc != 0:
        mylogs.error("mqtt: Unexpected disconnect with mqttserver. Result: " + str(rc))
        if(cfg.StopOnConnectionLost==1):
            mylogs.info("mqtt: LOST CONNECTION -> STOP ALL DEVICES")
            StartStopOperationCharger(0,1)
            StartStopOperationDisCharger(0,1)
    return

def mqtt_on_message(client, userdata, message):
    power = str(message.payload.decode("utf-8"))
    mylogs.debug("mqtt: Power message: " + power)
    #print("message received ", val)
    #print("message topic=",message.topic)
    #print("message qos=",message.qos)
    #print("message retain flag=",message.retain)
    process_power(round(int(power)))
    return

def mqtt_on_subscribe(client, userdata, mid, granted_qos):
    mylogs.info("mqtt: Qos granted: " + str(granted_qos))
    return


#add logger verbose
def verbose(self, message, *args, **kwargs):
    if self.isEnabledFor(logging.VERBOSE):
        self._log(logging.VERBOSE, message, args, **kwargs)

#######################################################################################################################################
#######################################################################################################################################
#                  *** Main ***                         ###############################################################################
#######################################################################################################################################

#################################################################
#Register exit functions
atexit.register(on_exit)
signal.signal(signal.SIGHUP,  handle_exit)  # 1
signal.signal(signal.SIGINT,  handle_exit)  # 2 Interrupt from keyboard CRTL-C mostly
signal.signal(signal.SIGQUIT, handle_exit)  # 3
signal.signal(signal.SIGTERM, handle_exit)  #15

#Ckeck if we should wait x seconds before start (Network interface up)
if len(sys.argv) == 2:
    try:
        s = int(sys.argv[1])
        sleep(s)
    except Exception as e:
        mylogs.error("ERROR IN SLEEP PARAMETER !\n")
        mylogs.error(str(e))

#################################################################
#Init global variables
status = Devicestatus();

#################################################################
#Get global cfg from file 

# Define a custom logging method for the new level
logging.VERBOSE = 15
logging.addLevelName(logging.VERBOSE, 'VERBOSE')
logging.Logger.verbose = verbose
#Create a new logger mylogs
mylogs  = logging.getLogger()

#Read conf file
spath   = os.path.dirname(os.path.realpath(sys.argv[0]))
status.configfile = spath + "/BSsetup.conf"
cfg     = chargerconfig()

#put it into status class for easier status info for webserver
status.EstBatteryWh = cfg.EstBatteryWh

print("######################################################")
print("# THERE IS NO GURANTEE FOR AN ERROR FREE EXECUTION   #")
print("# YOU TAKE THE TOTAL RISK IF YOU USE THIS SCRIPT !!! #")
print("# ONLY FOR USE WITH LIFEPO4 CELLS !!!                #")
print("# BATTERIES CAN BE DANGEROUS !!!                     #")
print("# BE SURE YOU KNOW WHAT YOU ARE DOING !!             #")
print("# THE AUTHOR(S) IS NOT LIABLE FOR ANY DAMAGE !!      #")
print("# YOU HAVE BEEN WARNED !                             #")
print("######################################################")

if (cfg.i_changed_my_config == 0):
    print("PLEASE SET UP YOUR DEVICE IN BSsetup.conf !!")
    print("CHECK ALL PARAMETERS CAREFULLY !!!")
    print("BY SETTING TO 1 YOU ACCEPT THE USING THIS SCRIPT AT YOUR OWN RISK")
    sys.exit()


#Init all needed DevVariables with None
display     = None
mwcandev    = None
LT1         = None
LT2         = None
LT3         = None
jk          = None
mqttclient  = None

#################################################################
# Check Basic Paramter if they look ok
if(CheckPatameter() == 1):
    print("Someting wrong with yout paramaters - Check all settings")
    mylogs.error("\n\nSometing wrong with yout paramaters - Check all settings!\n")
    sys.exit(1)

#################################################################
#################################################################
#init average power calculation array
powervalarray = []
for x in range(max(1,max(cfg.ChargerPowerCalcCount,cfg.DisChargerPowerCalcCount))): 
    powervalarray.append(x)
status.powercalccount = max(cfg.ChargerPowerCalcCount,cfg.DisChargerPowerCalcCount)


#################################################################
#################################################################
############  L C D - S E C T I O N  ############################
############ INIT 1st to display info ###########################
#################################################################
# LCD/OLED INIT
if (cfg.Selected_LCD != 0):
    mylogs.info("Init display")
    if (cfg.Selected_LCD == 1):
        try:
          display = i2clcd(cfg.lcdi2cadr)
          display.lcd_clear()
        except Exception as e:
            mylogs.error("\n\nEXECETION INIT DISPLAY !\n")
            mylogs.error(str(e))
            sys.exit(1)

#################################################################
#################################################################
############  C H A R G E R - S E C T I O N  ####################
#################################################################
#################################################################
#CAN INIT for CAN device: 0=bic2200, 1=NPB
if (cfg.Selected_Device_Charger <=1):
    mylogs.verbose("OPEN CAN DEVICE: MEANWELL")

    #Init and get get Type of device
    try:
        mwcandev = mwcan(cfg.Selected_Device_Charger,cfg.USEDID,"",cfg.loglevel)
        mwt = mwcandev.can_up()
        mylogs.info(mwt)

    except Exception as e:
        mwcandev.can_down() #Exception -> close the bus
        mwcandev = None
        mylogs.error("\n\nEXCEPTION Meanwell Device not found !\n")
        mylogs.error(str(e))
        printlcd("Exception open CAN-device for Meanwell",str(e))
        sys.exit(1)

    #first stop the device directly after startup check the paramaters
    mylogs.info("Meanwell Operation STOP at startup")

    #First Stop the device to have a defind state
    StartStopOperationMeanwell(0,1,1)

    mylogs.debug(mwt + " Serial     : " + mwcandev.serial_read())
    mylogs.debug(mwt + " Firmware   : " + str(mwcandev.firmware_read()))
    mylogs.info(mwt +  " temperature: " + str(mwcandev.temp_read()/10) + " C")

    #Set ChargerMainVoltage of the charger to check the parameters, needs to be in value *100, 24 = 2400
    status.ChargerMainVoltage = mwcandev.dev_Voltage * 100

    #get grid voltage from meanwell device
    Voltage_IN = 0
    Voltage_IN = round(float(mwcandev.v_in_read()/10))
    Voltage_IN = Voltage_IN + cfg.Voltage_ACIN_correction
    mylogs.info("Grid Voltage: " + str(Voltage_IN) + " V")

##################
    #Meanwell BIC-2200 specific
    if (cfg.Selected_Device_Charger==0):
        #setup Bic2200
        MW_ChargeVoltCorr = cfg.MW_BIC_ChargeVoltCorr

        #set to charge mode first
        sc  = mwcandev.system_config(0,0)
        bic = mwcandev.BIC_bidirectional_config(0,0)
        mylogs.debug("BIC SystemConfig: " + str(sc) + " BiDirectionalConfig: " + str(bic))
        if ((not is_bit(sc,SYSTEM_CONFIG_CAN_CTRL)) or (not is_bit(bic,0))):
            print("MEANWELL BIC2200 IS NOT IN CAN CONTROL MODE OR BI DIRECTIONAL MODE OR NOT OFF DURING STARTUP WHICH IS NEEDED !!!\n")
            c = input("SET CONTROLS NOW ? (y/n): ")
            if(c == "y"):
                sc  = mwcandev.system_config(1,1)
                bic = mwcandev.BIC_bidirectional_config(1,set_bit(bic,0))
                print("YOU HAVE TO POWER CYCLE OFF/ON THE MEANWELL BIC2200 NOW BY YOURSELF !!")
                MW_EEPROM_Counter_INC(0)
                MW_EEPROM_Counter_INC(0)
            sys.exit(1)


# Because the initialisation of Meanwell BIC-2200 is at Charger section
# the init of BICDISCharger is already there
# here we check the DisCharge settings
#    if (cfg.Selected_Device_DisCharger == 0):
        status.DisCharger_efficacy_factor = cfg.BIC2200_efficacy_factor
        #set Min Discharge voltage
        rval = mwcandev.BIC_discharge_v(0,0)
        if(rval != cfg.StopDischargeVoltage  + cfg.MW_BIC_DisChargeVoltCorr):
            mwcandev.BIC_discharge_v(1,cfg.StopDischargeVoltage + cfg.MW_BIC_DisChargeVoltCorr)
            MW_EEPROM_Counter_INC(1)
            mylogs.info("SET DISCHARGE VOLTAGE: " + str(rval))
        else:
            mylogs.info("DISCHARGE VOLTAGE ALREADY SET: " + str(rval))

        if (cfg.MaxDisChargeCurrent > mwcandev.dev_MaxDisChargeCurrent):
            mylogs.warning("Config max Discharge current is too high ! " + str(cfg.MaxDisChargeCurrent))
            mylogs.warning("Use max charge current from device ! " + str(mwcandev.dev_MaxDisChargeCurrent))
            cfg.MaxDisChargeCurrent = mwcandev.dev_MaxDisChargeCurrent

        if (cfg.MinDisChargeCurrent < mwcandev.dev_MinDisChargeCurrent):
            mylogs.warning("Config min discharge current is too low ! " + str(cfg.MinDisChargeCurrent))
            mylogs.warning("Use min discharge current from device ! " + str(mwcandev.dev_MinDisChargeCurrent))
            cfg.MinDisChargeCurrent = mwcandev.dev_MinDisChargeCurrent

        #Read the current mode from BIC-2200
        status.BICChargeDisChargeMode = mwcandev.BIC_chargemode(0,0)

#######################
    #Meanwell NBP specific
    if (cfg.Selected_Device_Charger==1):
        #setup NPB
        MW_ChargeVoltCorr = cfg.MW_NPB_ChargeVoltCorr
        sc  = mwcandev.system_config(0,0)
        cuve = mwcandev.NPB_curve_config(0,0,0) #Bit 7 should be 0
        mylogs.debug("NPB SystemConfig: " + str(sc) + " CURVE_CONFIG: " + str(cuve))

        #Check EEPROM write disable (only available with a FW > 02/2024!)
        if(not is_bit(sc,SYSTEM_CONFIG_EEP_OFF)):
            mylogs.warning("NPB EEPROM WRITE BACK IS ENABLED. WITH A FIRMWARE > 02/2024 THIS CAN BE DISABLED")
            mylogs.warning("NBP SYSTEM CONFIG BIT " + str(SYSTEM_CONFIG_EEP_OFF))

            #Bit 7 is 1 --> Charger Mode             #check OFF during startup
        if ((is_bit(cuve,CURVE_CONFIG_CUVE)) or ((sc & 0b0000000000000110) != 0)):
            print("MEANWELL NPB IS NOT IN PSU MODE / NOT OFF during STARTUP OR EEPROM WRITE IS ENABLED!!!\n")
            c = input("SET PSU MODE NOW ? (y/n): ")
            if(c == "y"):
                cuve = mwcandev.NPB_curve_config(1,CURVE_CONFIG_CUVE,0) #Bit 7 should be 0
                sc = clear_bit(sc,1)
                sc = clear_bit(sc,2)
                sc  = mwcandev.system_config(1,sc) #bit 10 only set to 1
                print("YOU HAVE TO POWER CYCLE OFF/ON THE MEANWELL NPB NOW BY YOURSELF !!")
                MW_EEPROM_Counter_INC(0)
            sys.exit(1)

    #Set fixed charge voltage to device BIC and NPB
    rval = mwcandev.v_out_set(0,0)
    if(rval != cfg.FixedChargeVoltage + MW_ChargeVoltCorr):
        rval = mwcandev.v_out_set(1,cfg.FixedChargeVoltage + MW_ChargeVoltCorr)
        MW_EEPROM_Counter_INC(0)
        mylogs.info("SET CHARGE VOLTAGE: " + str(rval))
    else:
        mylogs.info("CHARGE VOLTAGE ALREADY SET: " + str(rval))

    #NPB and BIC
    if (cfg.MaxChargeCurrent > mwcandev.dev_MaxChargeCurrent):
        mylogs.warning("Config max charge current is too high ! " + str(cfg.MaxChargeCurrent))
        mylogs.warning("Use max charge current from device ! " + str(mwcandev.dev_MaxChargeCurrent))
        cfg.MaxChargeCurrent = mwcandev.dev_MaxChargeCurrent

    if (cfg.MinChargeCurrent < mwcandev.dev_MinChargeCurrent):
        mylogs.warning("Config min charge current is too low ! " + str(cfg.MinChargeCurrent))
        mylogs.warning("Use min charge current from device ! " + str(mwcandev.dev_MinChargeCurrent))
        cfg.MinChargeCurrent = mwcandev.dev_MinChargeCurrent

    #start BIC2200 imidiatelly if ForceBicAlwaysOn is set.
    if(cfg.ForceBicAlwaysOn == 1):
        mylogs.info("Meanwell BIC-2200 AlwaysOn set")
        #Set output to 0 to be sure that the BIC does not start in a high value
        rval = mwcandev.i_out_set(0,0)
        if (rval != mwcandev.dev_MinChargeCurrent):
            mylogs.info("Meanwell BIC-2200 Set MinChargeCurrent")
            mwcandev.i_out_set(1,mwcandev.dev_MinChargeCurrent)
            MW_EEPROM_Counter_INC(0)
        rval = mwcandev.BIC_discharge_i(0,0)
        if (rval != mwcandev.dev_MinDisChargeCurrent):
            mylogs.info("Meanwell BIC-2200 Set MinDisChargeCurrent")
            mwcandev.BIC_discharge_i(1,mwcandev.dev_MinDisChargeCurrent)
            MW_EEPROM_Counter_INC(1)
        StartStopOperationMeanwell(1,1,1)

#################################################################
#################################################################
############  D I S C H A R G E R - S E C T I O N  ##############
#################################################################
#################################################################

# Lumentree / Trucki init
if ((cfg.Selected_Device_DisCharger == 1) or (cfg.lt_foreceoffonstartup == 1)):
    #Init and get get Type of device
    mylogs.info("Lumentree Init discharger ...")

    if(cfg.Selected_Device_DisCharger == 1): #only if LT is really the DisCharger
        status.DisCharger_efficacy_factor = cfg.lt_efficacy_factor

    if ((cfg.Selected_Device_DisCharger != 1) and (cfg.lt_foreceoffonstartup == 1)): 
        mylogs.info("Lumentree Init FORCE OFF MODE ...")

    try:
        LT1 = lt232(cfg.lt1_device,cfg.lt1_address,cfg.loglevel)
        LT1.lt232_open()
        status.LT1_Temperature = int(LT1.readtemp())
    except Exception as e:
        mylogs.error("\n\nLumentree Device 1 not found !\n")
        mylogs.error(str(e))
        printlcd("EXCEPTION Lumentree1",str(e))
        sys.exit(1)

    mylogs.debug("LT1 temperature: " + str(status.LT1_Temperature))
    mylogs.debug("LT1 set output to 0")
    LT1.set_watt_out(0) #init with 0 #init with 0, force without any function above
    cfg.MaxDisChargeWATT = cfg.lt1_maxwatt

    if (cfg.lt_count > 1):
        try:
            LT2 = lt232(cfg.lt2_device,cfg.lt2_address,cfg.loglevel)
            LT2.lt232_open()
        except Exception as e:
            mylogs.error("\n\nLumentree Device 2 not found !\n")
            mylogs.error(str(e))
            printlcd("EXCEPTION Lumentree2",str(e))
            sys.exit(1)

        status.LT2_Temperature = int(LT2.readtemp())
        mylogs.debug("LT2 temperature: " + str(status.LT2_Temperature))
        mylogs.debug("LT2 set output to 0")
        LT2.set_watt_out(0) #init with 0, force without any function above
        cfg.MaxDisChargeWATT = cfg.MaxDisChargeWATT + cfg.lt2_maxwatt

    if (cfg.lt_count > 2):
        try:
            LT3 = lt232(cfg.lt3_device,cfg.lt3_address,cfg.loglevel)
            LT3.lt232_open()
        except Exception as e:
            mylogs.error("\n\nLumentree Device 3 not found !\n")
            mylogs.error(str(e))
            printlcd("EXCEPTION Lumentree3",str(e))
            sys.exit(1)

        status.LT3_Temperature = int(LT3.readtemp())
        mylogs.debug("LT3 temperature: " + str(status.LT3_Temperature))
        mylogs.debug("LT3 set output to 0")
        LT3.set_watt_out(0) #init with 0 #init with 0, force without any function above
        cfg.MaxDisChargeWATT = cfg.MaxDisChargeWATT + cfg.lt3_maxwatt

    Lumentree_Check() #Get The first voltage needed for later
    mylogs.info("MaxDisChargeWATT LT_calc.  : " + str(cfg.MaxDisChargeWATT))

#################################################################
# Discharge Simulator
if (cfg.Selected_Device_DisCharger == 255):
    mylogs.info("DISCHARGE Simulator used")

#calculate the multiplyer for the DisCharger_efficacy_factor
#is needed in % --> 94% = 6% loss --> need 1.06% more current to get the output
status.DisCharger_efficacy_factor = (200 - status.DisCharger_efficacy_factor) / 100
mylogs.info("DisCharger_efficacy_factor  : " + str(status.DisCharger_efficacy_factor))


#################################################################
#################################################################
############  B M S - S E C T I O N  ############################
#################################################################
#################################################################
# BMS INIT
if (cfg.Selected_BMS != 0):
    BMSstatus = BMS()
    mylogs.info("Init BMS")
    if (cfg.Selected_BMS == 2):
        try:
            jk = jkbms(cfg.bms_device,cfg.loglevel)
            jk.jkbms_open()
        except Exception as e:
            mylogs.error("\n\nJK BMS not found !\n")
            mylogs.error(str(e))
            printlcd("EXEPTION JKBMS",str(e))
            sys.exit(1)

    sleep(1) #wait until bus is ready
    GetBMSData()

#Now the Battery hardware should be initilized
#Read the first battery value to initilize voltage and BMS
#Just check all sources.
i = 1
while(((status.BatteryVoltage == 0) or (status.BMSSOC ==0)) and (i<10)):
    GetChargerVoltage()
    GetDisChargerVoltage()
    GetBatteryVoltage()
    GetBMSData()
    mylogs.info("Try to get Voltage and BMSSOC ...: " + str(i) + " Voltage: " + str(status.BatteryVoltage/100) + "V - BMSSOC: " + str(status.BMSSOC) + "%")
    i+=1
    sleep(1)

if(i>=10):
    mylogs.error("ERROR CAN NOT GET BATTERY VOLTAGE AND BMSSOC - STOP")
    sys.exit(1)



#################################################################
#################################################################
############  G P I O - S E C T I O N  ##########################
#################################################################
#################################################################
# GPIO Init
if (cfg.Use_GPIO != 0):
    GPIO.setmode(GPIO.BCM)
    if (cfg.gpio1 != 0):
        mylogs.info("GPIO INIT: GPIO1: " + str(cfg.gpio1))
        GPIO.setup(cfg.gpio1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(cfg.gpio1,GPIO.FALLING,callback = gpio_callback,bouncetime = 1000)

    if (cfg.gpio2 != 0):
        mylogs.info("GPIO INIT: GPIO2: " + str(cfg.gpio2))
        GPIO.setup(cfg.gpio2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(cfg.gpio2,GPIO.FALLING,callback = gpio_callback,bouncetime = 1000)

    if (cfg.gpio3 != 0):
        mylogs.info("GPIO INIT: GPIO3: " + str(cfg.gpio3))
        GPIO.setup(cfg.gpio3, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(cfg.gpio3,GPIO.FALLING,callback = gpio_callback,bouncetime = 1000)

    if (cfg.gpio4 != 0):
        mylogs.info("GPIO INIT: GPIO4: " + str(cfg.gpio4))
        GPIO.setup(cfg.gpio4, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(cfg.gpio4,GPIO.FALLING,callback = gpio_callback,bouncetime = 1000)

#################################################################
#################################################################
############  M E T E R - S E C T I O N  ########################
#################################################################
#################################################################
# mqtt init
if (cfg.GetPowerOption==0) or (cfg.mqttpublish==1):
#    global mqttclient

    try:
        mylogs.info("USE MQTT, Init ...")
        mqttclient = mqtt.Client("BatteryController",clean_session=False)
        mqttclient.on_connect    = mqtt_on_connect
        mqttclient.on_disconnect = mqtt_on_disconnect
        mqttclient.on_subscribe  = mqtt_on_subscribe
        if (cfg.GetPowerOption==0):
            mqttclient.on_message    = mqtt_on_message

        mqttclient.username_pw_set(cfg.mqttuser, cfg.mqttpass)
        mqttclient.connect(cfg.mqttserver, cfg.mqttport, 120)
        mqttclient.loop_start()
    except Exception as e:
        mylogs.error("MQTT EXCEPTION !")
        mylogs.error(str(e))
        printlcd("EXCEPTION MQTT",str(e))
        sys.exit(1)


#################################################################
# http get init
if (cfg.GetPowerOption==1):
    try:
        mylogs.info("USE HTTP for Meter: " + str(cfg.http_get_option))
        schedule.every(cfg.http_schedule_time).seconds.do(http_request)      # Start every Xs
        METER = meter(cfg.http_get_option, cfg.http_ip_address, cfg.http_ip_port, cfg.http_user, cfg.http_pass, cfg.http_vzl_UUID, cfg.http_emlog_meterindex, cfg.http_iobrogerobject, cfg.loglevel) 
    except Exception as e:
        mylogs.error("METER INIT EXCEPTION !")
        mylogs.error(str(e))
        sys.exit(1)

#################################################################
# Simulator
if (cfg.GetPowerOption==255):
    schedule.every(2).seconds.do(simulator_request)    # Start every 2s
    mylogs.debug("USE SIMULATOR for Meter")

#################################################################
# Start WebServer
if (cfg.Use_WebServer==1):
    try:
        server_class  = HTTPServer
        handler_class = WS
        server_address = (cfg.WSipadr, cfg.WSport)
        httpd = server_class(server_address, handler_class)
        httpd.socket.settimeout(0.1) #Prevent blocking the rest of the script
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
    if (cfg.Use_WebServer==1):
        httpd.handle_request() #handle webserver requests
    if (cfg.GetPowerOption==1) or (cfg.GetPowerOption==255):
        schedule.run_pending()
    sleep(0.10)                #prevent high CPU usage
