#!/usr/bin/env python3

# Script for automatic charging and discharge your Battery 
# Not suitable for productive use. 
# Use for demo purposes only !
# Use on own risk !

##########################################################################################
# Needed external python3 modules
# pip3 install pyserial
# pip3 install paho-mqtt
# pip3 install ifcfg
# pip3 install minimalmodbus
# pip3 install configupdater
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
# macGH 31.01.2024  Version 0.1.5: -added Webserver, EstWh Calculation, cleanup
# macGH 04.02.2024  Version 0.1.6: -added BatteryWh estimation

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
from configupdater import ConfigUpdater
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from subprocess import check_output

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
                      'Links: &nbsp;<a href="/">Show current Status</a>&nbsp;&nbsp;&nbsp;' + \
                      '<a href="/config">Show current config</a>&nbsp;&nbsp;&nbsp;' + \
                      '<a href="/bms">Show current bms status</a>&nbsp;&nbsp;&nbsp;' + \
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
            """This just generates an HTML document with the config paramters and include `message`
            """
            content = ''
            for attr, value in vars(cfg).items():
                content = content + self._gettableentry(attr,value)
                
            content = self._beginhtml(message,-1,'/config') + \
                      '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;">'+ \
                      '<tbody>'+ \
                      content + \
                      '</tbody>' + \
                      '</table>'+ \
                      self._endhtml()
                
            return content.encode("utf8")  # NOTE: must return a bytes object!

        def _bmshtml(self, message):
            """This just generates an HTML document with the bms paramters and include `message`
            """
            content = ''
            for attr, value in vars(BMSstatus).items():
                content = content + self._gettableentry(attr,value)
                
            content = self._beginhtml(message,30,'/bms') + \
                      '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;">'+ \
                      '<tbody>'+ \
                      content + \
                      '</tbody>' + \
                      '</table>'+ \
                      self._endhtml()
                
            return content.encode("utf8")  # NOTE: must return a bytes object!

        def _statushtml(self, message):
            """This just generates an HTML document that includes `message`
            """
            content = self._beginhtml(str(message),30,'/') + \
                      '<table style="border-collapse: collapse; width: 500px; height: 20px; border-style: solid;">\n'+ \
                      '<tbody>\n'+ \
                      self._gettableentry('CurrentWattValue',status.CurrentWattValue) + \
                      self._gettableentry('CurrentTotalWatt',status.CurrentTotalWatt) + \
                      self._gettableentry('CurrentAverageWatt',status.CurrentAverageWatt) + \
                      self._gettableentry('LastWattUsedInDevice',status.LastWattValueUsedinDevice) + \
                      self._gettableentry('ChargerEnabled',status.ChargerEnabled) + \
                      self._gettableentry('DisChargerEnabled',status.DisChargerEnabled) + \
                      self._gettableentry('BMSSOC',status.BMSSOC) + \
                      self._gettableentry('EstBatteryWh',round(status.EstBatteryWh/1000)) + \
                      self._gettableentry('BatteryVoltage',status.BatteryVoltage) + \
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
                """
                if(variable == 'Refresh'):
                    mylogs.info("WebServer: Refresh")
                    todo = 'Refresh done'
                    if(self.path == '/'):
                        self.wfile.write(self._statushtml("Read Status"))
                    if(self.path == '/config'):
                        self.wfile.write(self._confightml("Read config"))
                    if(self.path == '/bms'):
                        self.wfile.write(self._bmshtml("Read BMS status"))
                    return
                """                    
    
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
        self.CellCount                  = 0
        self.BMSCellVoltage             = []
        for x in range(24):
            self.BMSCellVoltage.append(x)
            self.BMSCellVoltage[x]      = 0

class Devicestatus:

    def __init__(self):
        self.configfile                 = ""
        self.LastMeterTime              = datetime.datetime.now()
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
        self.LastPowerArrayPosition     = 0 
        self.actchargercounter          = 100 # only change values after x METER values --> all 2 Seconds new value with chargercounter = 5 => 10seconds, first start ok -> 100
        self.waitchargercounter         = 0 
        self.DisCharger_efficacy_factor = float(0)
        self.WebAutoRefresh             = 0

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
            self.powercalccount            =  int(updater["Setup"]["powercalccount"].value)
    
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
            self.MaxDischargeCurrent       =  int(updater["Setup"]["MaxDischargeCurrent"].value)
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
            self.MeterUpdateCounter        =  int(updater["Setup"]["MeterUpdateCounter"].value)
            self.MW_EEPROM_COUNTER         =  int(updater["Setup"]["MW_EEPROM_COUNTER"].value)
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
            
            self.Selected_BMS              =  int(updater["Setup"]["Selected_BMS"].value)
            self.bms_device                =  updater["Setup"]["bms_device"].value
            self.BMSminSOC                 =  int(updater["Setup"]["BMSminSOC"].value)
            self.BMSRestartSOC             =  int(updater["Setup"]["BMSRestartSOC"].value)
    
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
                    self.WSipadr = check_output(['hostname', '-I']).decode().split()[0]
                except Exception as e:
                    mylogs.error("EXCEPTION ON GETTING LOCAL IP ADDRESS - USE EMPTY ONE")
                    mylogs.error(str(e))
                    self.WSipadr = ""
    
            mylogs.info("-- Main --                  ")
            mylogs.info("PowerCalcCount:             " + str(self.powercalccount))
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
            mylogs.info("MaxDischargeCurrent:        " + str(self.MaxDischargeCurrent))
            mylogs.info("ZeroDeltaDisChargeWATT:     " + str(self.ZeroDeltaDisChargeWATT))
    
            mylogs.info("LastDisChargePower_delta:   " + str(self.LastDisChargePower_delta))
            mylogs.info("Voltage_ACIN_correction:    " + str(self.Voltage_ACIN_correction))
            mylogs.info("ForceBicAlwaysOn:           " + str(self.ForceBicAlwaysOn))
            mylogs.info("BIC2000 efficacy_factor     " + str(self.BIC2200_efficacy_factor))
       
            mylogs.info("-- PowerMeter --            ")
            mylogs.info("GetPowerOption:             " + str(self.GetPowerOption))
            mylogs.info("MeterUpdateCounter:         " + str(self.MeterUpdateCounter))
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
            mylogs.info("USEDID:                     " + str(self.USEDID))
            mylogs.info("MW_EEPROM_COUNTER:          " + str(self.MW_EEPROM_COUNTER))
    
            mylogs.info("-- Lumentree --             ")
            mylogs.info("Lumentree efficacy_factor   " + str(self.lt_efficacy_factor))
            mylogs.info("Lumentree Count             " + str(self.lt_count))
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
    
            mylogs.info("-- BMS --                   ")
            mylogs.info("Selected_BMS:               " + str(self.Selected_BMS))
            mylogs.info("bms_device:                 " + str(self.bms_device))
            mylogs.info("BMSminSOC:                  " + str(self.BMSminSOC))
            mylogs.info("BMSRestartSOC:              " + str(self.BMSRestartSOC))
    
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

        updater["Setup"]["MW_EEPROM_COUNTER"].value = str(cfg.MW_EEPROM_COUNTER)
        updater["Setup"]["EstBatteryWh"].value      = str(cfg.EstBatteryWh)
        updater.update_file()
        return

    def __init__(self):
      self.iniread()
      return        



def runWS(server_class=HTTPServer, handler_class=WS, addr="localhost", port=9000):
    server_address = (addr, port)
    httpd = server_class(server_address, handler_class)

    mylogs.info("WEBSERVER START at port: " + str(port))
    httpd.serve_forever()
    return


def on_exit():
    try:
        mylogs.info("CLEAN UP ...")
        if (cfg.GetPowerOption==0):
            mylogs.info("CLEAN UP: Shutdown MQTT")
            if ("mqttclient" in globals()):
                mqttclient.on_message = "" #prevent any further message to be proceed
                mqttpublish(1)
                mylogs.info("CLEAN UP: mqtt unsubcribe: " + cfg.mqttsubscribe)
                mqttclient.unsubscribe(cfg.mqttsubscribe)
                mqttclient.unsubscribe(cfg.mqttsubscribe)
                mqttclient.disconnect()
                mqttclient.loop_stop()
    
        sleep(0.5) # wait to be sure that mqtt is really down and no new message will be proceed !
        StartStopOperationCharger(0,1)
        StartStopOperationDisCharger(0,1)
        #CAN close 0=bic2200, 1=NPB
        if (cfg.Selected_Device_Charger <=1):
            mylogs.info("CLEAN UP: Shutdown MEANWELL DEVICE")
            mylogs.info("Close CAN device")
            mwcandev.can_down()
            mylogs.info("MEANWELL EEPROM COUNTER: " + str(cfg.MW_EEPROM_COUNTER))
    #        cfg.iniwrite()
        
        if (cfg.Selected_Device_DisCharger == 1): #Lumentree
            mylogs.info("CLEAN UP: Shutdown LUMENTREE DEVICE(s)")
            LT1.lt232_close()
            if(cfg.lt_count > 1): LT2.lt232_close()
            if(cfg.lt_count > 2): LT3.lt232_close()
    
        if (cfg.Selected_BMS == 2):
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
    mylogs.info("SIGNAL TO STOP RECEIVED")
    sys.exit(0)


def CheckPatameter():
    if((cfg.CellvoltageMax > 365) or (cfg.CellvoltageMin < 250)):
        mylogs.error("\n\nCELL VOLTAGE TOO HIGH OR TOO LOW! Voltage: "+ str(cfg.CellvoltageMin) + " - " + cfg.CellvoltageMax + "\n")
        return 0
        
    if((status.ChargerMainVoltage / cfg.CellCount) != 300):
        mylogs.error("\n\nCHARGER DOES NOT FIT FOR YOUR BATTERY, TOO LOW/HIGH VOLTAGE !")
        mylogs.error("Charger Main Voltage: " + str(status.ChargerMainVoltage) + " - CellCount: " + str(cfg.CellCount))
        return 0

    if(cfg.MW_EEPROM_COUNTER > 4000000):
        mylogs.error("\n\nMEANWELL DEVICE EEPROM MAX WRITE REACHED! " + " - Counter: " + str(cfg.MW_EEPROM_COUNTER)+"\n")
        return 0
        
    if(cfg.BatteryVoltageSource == 0):
        mylogs.error("\n\nNO VOLTAGE SOURCE DEFINED!\n")
        return 0

    if((cfg.ForceBicAlwaysOn == 1) and ((cfg.Selected_Device_Charger + cfg.Selected_Device_DisCharger) != 0)):
        mylogs.error("\n\nYOU CAN ONLY USE ForceBicAlwaysOn WITH BIC2200 AS CHARGER AND DISCHARGER !\n")
        return 0

    #looks good continue
    mylogs.info("Parameter check OK")
    return 1


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
            mylogs.info("GPIO CALLBACK 2 - Nothing to do here")
    
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
        mylogs.info("-> STATUS:  C:" + str(status.ChargerEnabled) + "  D:" + str(status.DisChargerEnabled) + " | SOC:" + str(status.BMSSOC) + "%  BattV:" + str(status.BatteryVoltage/100) + "V |  Total: " + str(status.CurrentTotalWatt) + "W  Meter:" + str(status.CurrentWattValue) + "W  Average: " + str(status.CurrentAverageWatt) + "W  LOUT:" + str(status.LastWattValueUsedinDevice) + "W - RCAP: " + str(round(status.EstBatteryWh/1000)) )

#####################################################################
# LCD routine
#####################################################################
def printlcd(line1="", line2=""):
    try:
        display.lcd_clear()
        if (line1==""): 
            if(status.LastWattValueUsedinDevice > 0):
                line1 = "PW:" + "{:<5}".format(str(status.CurrentWattValue))  + " O:" + str(status.LastWattValueUsedinDevice)
            else:
                line1 = "PW:" + "{:<5}".format(str(status.CurrentWattValue))  + " I:" + str(status.LastWattValueUsedinDevice)
            
        if (line2==""): line2 = "SC:" + "{:<6}".format(str(status.BMSSOC)+"%") + "C:" + str(status.ChargerEnabled) + " D:" + str(status.DisChargerEnabled)

        
        if (cfg.Selected_LCD == 1):
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
def bms_read():
    if (cfg.Selected_BMS == 0): #disabled return always full, you should really use a SOC methode ! 
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

          BMSstatus.CellCount  = jk.cell_count
          BMSstatus.BMSSOC     = jk.soc
          BMSstatus.BMSCurrent = jk.act_current
          BMSstatus.BMSVoltage = jk.voltage
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
#Setup Operation mode of charger
def StartStopOperationCharger(val,force=0):
    mylogs.verbose("StartStopOperationCharger: " + str(val) + " Force: " + str(force))
    
    if (status.ChargerEnabled == 0):
        val = 0

    #if the Battery is not full anymore, start recharging
    if((status.BatteryFULL == 1) and (status.BatteryVoltage <= cfg.RestartChargevoltage)):
         mylogs.info("StartStopOperationCharger: Battery charging allowed again. Current Volatge: " + str(status.BatteryVoltage/100) + " (Restart Voltage: " + str(cfg.RestartChargevoltage/100) + ")")
         status.BatteryFULL = 0

    #Battery is full, stop charing and wait for discharge
    if((status.ChargerStatus  == 1)  and (status.LastChargerGetCurrent <= cfg.StopMinChargeCurrent)): # and (status.LastChargerGetCurrent != 0)):
        status.BatteryFULL = 1
        force = 1 #force stop charging 

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
            mylogs.verbose("No change to Charger output, Delta is: " + str(p) + "  - Set to :" + str(cfg.LastChargePower_delta))
            return

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
    mylogs.verbose("StartStopOperationDisCharger: " + str(val) + " Force: " + str(force))
    
    if (status.DisChargerEnabled == 0):
        mylogs.verbose("StartStopOperationDisCharger: DisCharger disabled !")
        val = 0

    #if the Battery is not totally empty anymore, start Discharging
    if((status.BatteryEMPTY == 1) and (status.BatteryVoltage >= cfg.RestartDisChargevoltage) and (status.BMSSOC >=cfg.BMSRestartSOC)):
        mylogs.info("StartStopOperationDisCharger: Battery Discharging allowed again. Current Volatge: " + str(status.BatteryVoltage/100) + " (Restart Voltage: " + str(cfg.RestartDisChargevoltage/100) + ")")
        status.BatteryEMPTY = 0

    #Battery is empty, stop Discharing and wait for charging
    if((status.BatteryVoltage > 0) and (status.BatteryVoltage <= cfg.StopDischargeVoltage)):
        status.BatteryEMPTY = 1
        #Set EstBatteryWh to 0, because for this schript the Battery is empty 
        cfg.EstBatteryWh    = 0

    if(status.BatteryEMPTY == 1):
        mylogs.info("StartStopOperationDisCharger: Battery EMPTY ! Battery Voltage: " + str(status.BatteryVoltage/100) + ' - SOC: ' + str(status.BMSSOC))
        val = 0

    if (force==0): #if force = 1, proceeed without any logic 
        # Do not discharge any further if SOC is lower than specified
        if ((status.BMSSOC <= cfg.BMSminSOC) or (status.BatteryVoltage <= cfg.StopDischargeVoltage)):
            val = 0 
            mylogs.info("StartStopOperationDisCharger: SOC or Voltage too low: " + str(status.BMSSOC) + "% or " + str(status.BatteryVoltage) + "V ->  SET VALUE TO: " + str(val))

        if(status.DisChargerStatus == 0) and (val == 0): 
            mylogs.verbose("StartStopOperationDisCharger: Already off mode")
            return #DisCharger already off, can stop here
        

        #Check if we need to set the new value to the DisCharger
        p = abs((status.LastWattValueUsedinDevice + status.ZeroExportWatt) - val)
        
        if ((val != 0) and (p <= cfg.LastDisChargePower_delta)): #0:must be processed
            mylogs.info("No change to DisCharger. Delta is: " + str(p) + " (of: " + str(cfg.LastDisChargePower_delta) + ") - Last Value: " + str(status.LastWattValueUsedinDevice) + " (ZeroExport: " + str(cfg.ZeroDeltaDisChargeWATT) + ") - New: " + str(val))
            return

    Newval = val      #used for calculation
    status.ZeroExportWatt = 0
    if (cfg.ZeroDeltaDisChargeWATT > 0):
        if (val > cfg.ZeroDeltaDisChargeWATT):
            Newval = val - cfg.ZeroDeltaDisChargeWATT
            status.ZeroExportWatt = cfg.ZeroDeltaDisChargeWATT
            mylogs.info("ZEROExport: " + str(val) + " -> " + str(Newval) + " (Delta: " + str(cfg.ZeroDeltaDisChargeWATT) + ")")


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
# Operation Meanwell
def StartStopOperationMeanwell(val, force=0):
    mylogs.verbose("StartStopOperationMeanwell value: " + str(val) + " Force: " + str(force))
    #read current status from device
    
    if((cfg.Selected_Device_Charger == 0) and (cfg.ForceBicAlwaysOn) and (force==0)):
        return 1
    
    opmode = mwcandev.operation(0,0)
    mylogs.debug("Meanwell: Operation mode: " + str(opmode))
    if (val == 0): #set to off  
        if((opmode != 0) or (force==1)):
            mwcandev.operation(1,0)
            mylogs.verbose("Meanwell: Operation mode set to: OFF")
            cfg.MW_EEPROM_COUNTER += 1
        else:
            mylogs.verbose("Meanwell: Operation mode already OFF")
    else:
        if((opmode != 1) or (force==1)):
            mwcandev.operation(1,1)   
            mylogs.verbose("Meanwell: Operation mode set to: ON")
            cfg.MW_EEPROM_COUNTER += 1
        else:
            mylogs.verbose("Meanwell: Operation mode already ON")



#    if (val == 0):  
#        if (status.ChargerStatus != 0):
#            mwcandev.operation(1,0)
#            status.ChargerStatus = 0
#            status.ZeroImportWatt = 0   
#            mylogs.debug("Meanwell: Operation mode set to: OFF")
#            cfg.MW_EEPROM_COUNTER += 1
#        else:
#            mylogs.debug("Meanwell: Operation mode already OFF")
#    else:
#        if (status.ChargerStatus != 1):
#            mwcandev.operation(1,1)   
#            status.ChargerStatus = 1   
#            mylogs.debug("Meanwell: Operation mode set to: ON")
#            cfg.MW_EEPROM_COUNTER += 1
#        else:
#            mylogs.debug("Meanwell: Operation mode already ON")
   
    return val


def DisCharger_BIC2200_Set(val,force=0):
    mylogs.verbose("DisCharger_BIC2200_Set value: " + str(val) + " Force: " + str(force))

    status.BICChargeDisChargeMode = mwcandev.BIC_chargemode(0,0)
    if(status.BICChargeDisChargeMode==0):
        mylogs.info("StartStopOperationDisCharger: Set BIC2200 to DisCharge Mode")
        mwcandev.BIC_chargemode(1,1)  #set BIC to DisChargemode
        cfg.MW_EEPROM_COUNTER += 1
#        status.BICChargeDisChargeMode=1

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
    ZeroDelta = int((cfg.ZeroDeltaDisChargerWatt / vout)*10000)
    mylogs.info("ZERODELTA IS: " + str(ZeroDelta))
    status.ZeroExportWatt = 0 #Reset to 0 and see if we need it later

    #BIC device has a minimal DisCharge current
    #Stop if this value is reached or allow take power from grid to charge 
    if (IntCurrent <= cfg.MinDisChargeCurrent):
        if (IntCurrent < (cfg.MinDisChargeCurrent - ZeroDelta)):
            mylogs.info("Meanwell BIC: Current too small - " + str(IntCurrent) + " - MinCurrent: " + str(cfg.MinDisChargeCurrent) + " - ZeroDelta: " + str(ZeroDelta)+ " -> Device OFF")
            IntCurrent = 0;
            OPStart = False 
        else:
            IntCurrent = cfg.MinDisChargeCurrent
            status.ZeroImportWatt = cfg.ZeroDeltaChargerWatt
            mylogs.info("Meanwell BIC: ZeroExportWatt used - " + str(cfg.ZeroDeltaDisChargerWatt))

    if (IntCurrent != status.LastDisChargerCurrent):
        if (status.actchargercounter >= cfg.MeterUpdateCounter):
            mylogs.info("Meanwell BIC: Set new current to: " + str(IntCurrent) + "  (Last current: " + str(status.LastDisChargerCurrent) + ")")
            c = mwcandev.BIC_discharge_i(1,IntCurrent)
            status.LastDisChargerCurrent = IntCurrent;
            cfg.MW_EEPROM_COUNTER += 1
        else:
            mylogs.verbose("Meanwell BIC: Wait for next change: " + str(status.actchargercounter) + "  of: " + str(cfg.MeterUpdateCounter))
            status.actchargercounter += 1
    else:
        mylogs.info("Meanwell BIC: No New current to set. Last current: " + str(status.LastDisChargerCurrent))
        
    
    #try to set the new ChargeCurrent if possible
    if (OPStart == True): #if true start mw device 
        mylogs.verbose("OPSTART TRUE : Start Meanwell Device")
        status.DisChargerStatus  = 1
        StartStopOperationMeanwell(1,force)
    else: 
        mylogs.verbose("OPSTART FALSE: Stop Meanwell Device")
        status.DisChargerStatus  = 0
#        status.ZeroExportWatt = 0
        StartStopOperationMeanwell(0,force)     

    sleep(0.3)
    iout  = mwcandev.i_out_read()
    NewVal = int((iout*vout)/10000)

    mylogs.info("Meanwell BIC: W Battery_Vout:" + str(vout/100) + ":V: Battery_I_out:" + str(iout/100) + ":A: I Calc:" + str(IntCurrent) + " = " + str(IntCurrent/100) + ":A --> WATT: " + str(NewVal))

    status.LastWattValueUsedinDevice = NewVal
    return


def Charger_Meanwell_Set(val,force=0):
    mylogs.verbose("Charger_Meanwell_Set value: " + str(val) + " Force: " + str(force))

    #For BIC set Charge mode first
    if cfg.Selected_Device_Charger == 0: #BIC2200
        status.BICChargeDisChargeMode = mwcandev.BIC_chargemode(0,0)
        if(status.BICChargeDisChargeMode==1):
            mylogs.info("StartStopOperationCharger: Set BIC2200 to Charge Mode")
            mwcandev.BIC_chargemode(1,0)  #set BIC to Chargemode
            cfg.MW_EEPROM_COUNTER += 1
#            cfg.BICChargeDisChargeMode=0

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
            mylogs.info("Meanwell: Current too small - " + str(IntCurrent) + " - MinCurrent: " + str(cfg.MinChargeCurrent) + " - ZeroDelta: " + str(ZeroDelta) + " = " + str(IntCurrent+ZeroDelta) + " -> Device OFF")
            IntCurrent = 0;
            OPStart = False 
        else:
            IntCurrent = cfg.MinChargeCurrent
            status.ZeroImportWatt = int((cfg.MinChargeCurrent - ZeroDelta)*vout/10000)
            mylogs.info("Meanwell: ZeroImportWatt used - allow from GRID: " + str(status.ZeroImportWatt))

    if (IntCurrent != status.LastChargerSetCurrent):
        if ((status.actchargercounter >= cfg.MeterUpdateCounter) or (force == 1)):
            mylogs.info("Meanwell: >>>> Set new current to: " + str(IntCurrent) + "  (Last current set: " + str(status.LastChargerSetCurrent) + ") <<<<")
            
            if(IntCurrent == 0):
                #Probably no need to set since device will be set to OFF mode
                #c = mwcandev.i_out_set(1,IntCurrent)
                #cfg.MW_EEPROM_COUNTER += 1
                mylogs.info("Meanwell: IntCurrent = 0")
                status.LastChargerSetCurrent = IntCurrent;
                OPStart = False #device start
            else:
                if((status.LastChargerGetCurrent < (status.LastChargerSetCurrent-50)) and (status.BMSSOC > 98)):
                    mylogs.info("Meanwell: >>>> NO SET -> BATTERY ALMOST FULL: " + str(IntCurrent) + " (Last current GET: " + str(status.LastChargerGetCurrent)  + "  (Last current SET: " + str(status.LastChargerSetCurrent) + ") <<<<")
                    OPStart = True #device start or continue
                else:
                    mylogs.info("Meanwell: SET NEW CURRENT TO: " + str(IntCurrent))
                    c = mwcandev.i_out_set(1,IntCurrent)
                    status.LastChargerSetCurrent = IntCurrent;
                    cfg.MW_EEPROM_COUNTER += 1
                    OPStart = True #device start or continue
                    
            status.actchargercounter = 1 #Reset counter to 1 
        else:
            mylogs.verbose("Meanwell: Wait for next change: " + str(status.actchargercounter) + "  of: " + str(cfg.MeterUpdateCounter))
            status.actchargercounter += 1
            if(status.ChargerStatus == 0):#do not change the current status
                OPStart = False
            else:
                OPStart = True             
    else:
        if(IntCurrent != 0):
            mylogs.info("Meanwell: No New current to set. Last current: " + str(status.LastChargerSetCurrent))
            OPStart = True #device start or continue
        
              
#    if(OPStart):
#        status.ChargerStatus  = 1
#    else:
#        status.ChargerStatus  = 0
#        status.ZeroImportWatt = 0
       


    #try to set the new ChargeCurrent if possible
    if (OPStart == True): #if true start mw device 
        mylogs.verbose("OPSTART TRUE : Start Meanwell Device")
        status.ChargerStatus  = 1
        StartStopOperationMeanwell(1,force)
    else: 
        mylogs.verbose("OPSTART FALSE: Stop Meanwell Device")
        status.ChargerStatus  = 0
        status.ZeroImportWatt = 0
        StartStopOperationMeanwell(0,force)     

    #wait to read the current after MW starts to get a value != 0
    #if 0 returns Battery is full, checked in StartStopCharger
    sleep(0.3)
    status.LastChargerGetCurrent  = mwcandev.i_out_read()
    NewVal = int((status.LastChargerGetCurrent*vout)/10000)
    mylogs.info("Meanwell: Battery_Vout:" + str(vout/100) + ":V: I_out:" + str(status.LastChargerGetCurrent/100) + ":A: I Calc:" + str(IntCurrent/100) + ":A - GET ACT: " + str(NewVal) + "W")
    status.LastWattValueUsedinDevice = NewVal*(-1)

    return OPStart



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
        sleep(0.3)
        
        LT1.lt232_open()
        if (cfg.lt_count > 1): LT2.lt232_open()
        if (cfg.lt_count > 2): LT3.lt232_open()

    except Exception as e:
        mylogs.error("\n\n LUMENTREE REOPEN FAILED !\n")
        mylogs.error(str(e))
    return    

#####################################################################
# Check periodically if Lumentree is still online. If not try to reopen
def Lumentree_Check():
    if (cfg.Selected_Device_DisCharger != 1): return

    mylogs.verbose("------> Lumentree Check Alive ...")
    try:
        status.DisChargerVoltage = LT1.readDCvoltage() * 10 #return 3 digits, need 4 for compare --> *10
#        sleep(0.1)
#        LTstatus = LT1.readtemp() # not really needed
        mylogs.debug("------> Lumentree Check Alive OK. BattVoltage: " + str(status.DisChargerVoltage)) # + " - Temperature: " + str(LTstatus))
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
    mylogs.verbose("DisCharger_Lumentree_Set to value: " + str(val))

    if (cfg.MaxDisChargeWATT <= val):
        outpower = cfg.MaxDisChargeWATT
    else:
        if (cfg.MinDisChargeWATT >= val):
            outpower = 0     #Stop DisCharger, too low Watt needed
        else:
            outpower = val
    
    if (val==0): outpower = 0
    
    if (force==0):
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
                mylogs.info("DisCharger_Lumentree_Set: DC volatge too low. Probably Battery empty : " + str(DCvoltage))
                return
            else:
                #Disable DisCharger
                outpower = 0

    sleep(0.1)  #wait 0.2 seconds to read next value

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
        sleep(0.2)  #wait 0.2 seconds to read next value
        status.LastWattValueUsedinDevice = LT1.read_watt_out()
    
        #Lumentree Inverter 2
        if (cfg.lt_count > 1):
            mylogs.verbose("DisCharger_Lumentree_Set   (2) : " + str(outpower2))
            LT2.set_watt_out(outpower2);
            sleep(0.2)  #wait 0.2 seconds to read next value
            status.LastWattValueUsedinDevice = status.LastWattValueUsedinDevice + LT2.read_watt_out()
            
        #Lumentree Inverter 3
        if (cfg.lt_count > 2):
            mylogs.verbose("DisCharger_Lumentree_Set   (3) : " + str(outpower3))
            LT3.set_watt_out(outpower3);
            sleep(0.2)  #wait 0.2 seconds to read next value
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

    except:
        mylogs.error("GetChargerVoltage EXEPTION !")
        mylogs.error(str(e))
    return status.ChargerVoltage


def GetDisChargerVoltage():
    mylogs.debug("GetDisChargerVoltage ...")
    try:
        if (cfg.Selected_DisDevice_Charger == 0): #BIC2200
            status.DisChargerVoltage = mwcandev.v_out_read()
            
        if (cfg.Selected_DisDevice_Charger == 1): #Lumentree
            #status.DisChargerVoltage = LT1.readDCvoltage() * 10 #return 3 digits, need 4 for compare --> *10
            mylogs.info("GetDisChargerVoltage: Nothing to do here, this is already done in Lumentree_Check !")

    except:
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

    except:
        mylogs.error("GetBatteryVoltage EXEPTION !")
        mylogs.error(str(e))
    
    return

def CalcBatteryWh():
    mylogs.debug("CalcBatteryWh ...")
    
    if(status.LastWattValueUsedinDevice <= 0):
        EF = 1 #Charger do not need a correction
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

#####################################################################
#calculate the output power by array
#####################################################################
def getoutputpower(val):
    mylogs.debug("getoutputpower ...")

    try:
        status.ProcessCount+=1
        if(status.ProcessCount > 20): #every 20 power value reads, if set to 2 seconds --> all 40 seconds 
            status.ProcessCount = 1
            bms_read()  #Read all data and set some status IDs
            Lumentree_Check()  #Check every minute if LT is online, and get CD Voltage, if not try to reconnect
            GetBatteryVoltage()
            
        #check the total Watt, 
        status.CurrentWattValue = val;
        status.CurrentTotalWatt = status.CurrentWattValue + status.LastWattValueUsedinDevice
     
        mylogs.debug("CurrentTotalWatt         : " + str(status.CurrentTotalWatt))
        mylogs.debug("LastWattValueusedinDevice: " + str(status.LastWattValueUsedinDevice))
        #add new value to array
        status.LastPowerArrayPosition += 1
        if (status.LastPowerArrayPosition >= cfg.powercalccount):
             status.LastPowerArrayPosition = 0
        powervalarray[status.LastPowerArrayPosition] = status.CurrentTotalWatt
        #get avergae value of array
        r = round(sum(powervalarray) / cfg.powercalccount)
        #mylogs.info("Power average: " + str(r))
        
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
    mylogs.debug("process_power: " + str(power))
    NewPower = getoutputpower(power)
    
    OPStart = False #should the device do something
    curtime = datetime.datetime.now()
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
        
        if (status.ZeroImportWatt > 0):      #charger take small power from Grid for charging, check if still valid
            if((NewPower - status.ZeroImportWatt) > cfg.ZeroDeltaChargerWatt):
                status.ZeroImportWatt = 0   #too much delta, reset and use normal way
            else:
                mylogs.verbose("ChargeMethod: 1 with ZeroImport")
                StartStopOperationCharger(NewPower)
                return power
        
        # Charge / Discharge calculation
        # charge, getting power from PV, charge battery now 
        if (NewPower) < 0:
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
#    if (cfg.PowerControlmethod == 2):
#        print("Method 2")


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
        mylogs.debug("http: Power message: " + str(power))
        
    except Exception as e:
        mylogs.error("HTTP CONNECTION ERROR")
        mylogs.error(str(e))
        #Stop Operation if setting set
        if(cfg.StopOnConnectionLost==1):
            StartStopOperationCharger(0)
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
            StartStopOperationCharger(0)  
            StartStopOperationDisCharger(0)
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
signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGHUP,  handle_exit)
signal.signal(signal.SIGQUIT, handle_exit)
signal.signal(signal.SIGINT,  handle_exit)   #Interrupt from keyboard CRTL-C mostly

#for sig in [signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT, signal.SIGKILL]:
#    signal.signal(sig, handle_exit)
    
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

if (cfg.i_changed_my_config == 0):
    print("PLEASE SET UP YOUR DEVICE IN BSsetup.conf !!")
    print("THERE IS NO GURANTEE FOR AN ERROR FREE EXECUTION")
    print("YOU TAKE THE TOTAL RISK IF YOU USE THIS SCRIPT !!!")
    print("ONLY FOR USE WITH LIFEPO4 CELLS !!!")
    print("BATTERIES CAN BE DANGEROUS !!!")
    print("CHECK ALL PARAMETERS CAREFULLY !!!")
    sys.exit()


#################################################################
#init average power calculation array
powervalarray = []
for x in range(max(1,cfg.powercalccount)): 
    powervalarray.append(x)

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
            mylogs.error("\n\nERROR INIT DISPLAY !\n")
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
    mwcandev = mwcan(cfg.Selected_Device_Charger,cfg.USEDID,"",cfg.loglevel)
    
    #Init and get get Type of device
    try:
        mwt = mwcandev.can_up()
        mylogs.info(mwt)
    except Exception as e:
        mylogs.error("\n\nMeanwell Device not found !\n")
        mylogs.error(str(e))
        printlcd("EXEPT Meanwell",str(e))
        sys.exit(1)
    
    #print(mwcandev.serial_read())
    mylogs.info(mwt + " temperature: " + str(mwcandev.temp_read()/10) + " C")
    
    #Set ChargerMainVoltage of the charger to check the parameters, needs to be in value *100, 24 = 2400
    status.ChargerMainVoltage = mwcandev.dev_Voltage * 100
    
    #get grid voltage from meanwell device
    Voltage_IN = 0
    Voltage_IN = round(float(mwcandev.v_in_read()/10)) 
    Voltage_IN = Voltage_IN + cfg.Voltage_ACIN_correction  
    mylogs.info("Grid Voltage: " + str(Voltage_IN) + " V")
    
    #Set main parameter and stop device
    mylogs.debug("Operation STOP: " + str(mwcandev.operation(1,0)))
    StartStopOperationCharger(0,1)

    #Set fixed charge voltage to device BIC and NPB
    rval = mwcandev.v_out_set(0,0)
    if(rval != cfg.FixedChargeVoltage):
        rval = mwcandev.v_out_set(1,cfg.FixedChargeVoltage)
        cfg.MW_EEPROM_COUNTER += 1
        mylogs.info("SET CHARGE VOLTAGE: " + str(rval))
    else:
        mylogs.info("CHARGE VOLTAGE ALREADY SET: " + str(rval))

    #Meanwell BIC-2200 specific
    if (cfg.Selected_Device_Charger==0):
        #setup Bic2200
        #set to charge mode first
        status.DisCharger_efficacy_factor = cfg.BIC2200_efficacy_factor

        sc  = mwcandev.system_config(0,0)
        bic = mwcandev.BIC_bidirectional_config(0,0)
        if (is_bit(sc,SYSTEM_CONFIG_CAN_CTRL) or is_bit(bic,0)):
            print("MEANWELL BIC2200 IS NOT IN CAN CONTROL MODE OR BI DIRECTIONAL MODE WHICH IS NEEDED !!!\n")
            c = input("SET CONTROLS NOW ? (y/n): ")
            if(c == "y"):
                sc  = mwcandev.mwcandev.system_config(1,set_bit(sc,0))
                bic = mwcandev.mwcandev.BIC_bidirectional_config(1,set_bit(bic,0))
                print("YOU HAVE TO POWER CYCLE OFF/ON THE MEANWELL BIC2200 NOW BY YOURSELF !!")
                cfg.MW_EEPROM_COUNTER += 2
            sys.exit(1) 
        
        c = mwcandev.BIC_chargemode(0,0)
        if(c==1):
            c = mwcandev.BIC_chargemode(1,0)
            cfg.MW_EEPROM_COUNTER += 1
            
        status.BICChargeDisChargeMode = 0
        
        #start BIC2200 imidiatelly if ForceBicAlwaysOn is set
        if(cfg.ForceBicAlwaysOn):
            StartStopOperationMeanwell(1,1)
            

    #Meanwell NBP specific
    if (cfg.Selected_Device_Charger==1):
        #setup NPB
        cuve = mwcandev.NPB_curve_config(0,0,0) #Bit 7 should be 0
        if (is_bit(cuve,CURVE_CONFIG_CUVE)):    #Bit 7 is 1 --> Charger Mode
            print("MEANWELL NPB IS NOT IN PSU MODE WHICH IS NEEDED !!!\n")
            c = input("SET PSU MODE NOW ? (y/n): ")
            if(c == "y"):
                cuve = mwcandev.NPB_curve_config(1,CURVE_CONFIG_CUVE,1) #Bit 7 should be 0
                print("YOU HAVE TO POWER CYCLE OFF/ON THE MEANWELL NPB NOW BY YOURSELF !!")
                cfg.MW_EEPROM_COUNTER += 1
            sys.exit(1) 
        
    if (cfg.MaxChargeCurrent > mwcandev.dev_MaxChargeCurrent):
        mylogs.error("Config max charge current is too high ! " + str(cfg.MaxChargeCurrent))
        mylogs.error("Use max charge current from device ! " + str(mwcandev.dev_MaxChargeCurrent))
        cfg.MaxChargeCurrent = mwcandev.dev_MaxChargeCurrent
        sys.exit(1)

    if (cfg.MinChargeCurrent < mwcandev.dev_MinChargeCurrent):
        mylogs.error("Config min charge current is too low ! " + str(cfg.MinChargeCurrent))
        mylogs.error("Use min charge current from device ! " + str(mwcandev.dev_MinChargeCurrent))
        cfg.MinChargeCurrent = mwcandev.dev_MinChargeCurrent
        sys.exit(1)

#################################################################
#################################################################
############  D I S C H A R G E R - S E C T I O N  ##############
#################################################################
#################################################################

# Meanwell BIC-2200
if (cfg.Selected_Device_DisCharger == 0): 
    #set Min Discharge voltage
    rval = mwcandev.BIC_discharge_v(0,0)
    if(rval != cfg.StopDischargeVoltage):
        mwcandev.BIC_discharge_v(1,cfg.StopDischargeVoltage)
        cfg.MW_EEPROM_COUNTER += 1
        mylogs.info("SET DISCHARGE VOLTAGE: " + str(rval))
    else:
        mylogs.info("DISCHARGE VOLTAGE ALREADY SET: " + str(rval))


# BIC2000
# Because the initialisation of Meanwell is at Charger section
# the init of BICDISCharger is also there


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
        LTtemp = LT1.readtemp()
    except Exception as e:
        mylogs.error("\n\nLumentree Device 1 not found !\n")
        mylogs.error(str(e))
        printlcd("EXEPT Lumentree1",str(e))
        sys.exit(1)
    
    mylogs.debug("LT1 temperature: " + str(LTtemp))
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
            printlcd("EXEPT Lumentree2",str(e))
            sys.exit(1)
        
        LTtemp = LT2.readtemp()
        mylogs.debug("LT2 temperature: " + str(LTtemp))
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
            printlcd("EXEPT Lumentree3",str(e))
            sys.exit(1)
        
        LTtemp = LT3.readtemp()
        mylogs.debug("LT3 temperature: " + str(LTtemp))
        mylogs.debug("LT3 set output to 0")
        LT3.set_watt_out(0) #init with 0 #init with 0, force without any function above
        cfg.MaxDisChargeWATT = cfg.MaxDisChargeWATT + cfg.lt3_maxwatt

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
            printlcd("EXEPT JKBMS",str(e))
            sys.exit(1)

    sleep(0.5) #wait until bus is ready
    bms_read()
    

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
    global mqttclient
    
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
        printlcd("EXEPT MQTT",str(e))
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
    schedule.every(2).seconds.do(simulator_request)                      # Start every 2s
    mylogs.debug("USE SIMULATOR for Meter")


#################################################################
# Start WebServer
if (cfg.Use_WebServer==1):
    try:
        runWS(addr=cfg.WSipadr, port=cfg.WSport)
    except Exception as e:
        mylogs.error("EXCEPTION STARTING WEBSERVER")
        mylogs.error(str(e))
        sys.exit(1)        

#################################################################
#################################################################
# Finally check the Paramter if they look good
if(CheckPatameter() == 0):
    print("Someting wrong with yout paramaters - Check all settings")
    mylogs.error("\n\nSometing wrong with yout paramaters - Check all settings!\n")
    sys.exit(1)

#################################################################
#################################################################
############  M A I N  - S E C T I O N  #########################
#################################################################
#################################################################
while True:
    if (cfg.GetPowerOption==1) or (cfg.GetPowerOption==255):
        schedule.run_pending()
    sleep(0.10)      #prevent high CPU usage
