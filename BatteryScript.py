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
import logging
import random
from configupdater import ConfigUpdater
import paho.mqtt.client as mqtt
import RPi.GPIO as GPIO

from Meanwell.mwcan import *
from Lumentree.lt232 import *
from BMS.jkbms import *
from Meter.meter import *

#LCD import
from LCD.hd44780_i2c import i2clcd

#########################################
##class config
class Devicestatus:

    def __init__(self):
        self.configfile                 = ""
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
        self.ZeroExportWatt             = 0
        self.ZeroImportWatt             = 0
        self.BatteryFULL                = 0   #0=no, 1=Full
        self.BatteryEMPTY               = 0   #0=no, 1=EMPTY
        self.BatteryVoltage             = 0   # Battery Voltage to check charging status, this is used for calculation 
        self.BMSSOC                     = 100 # Battery State of Charge status if BMS is used, if not 100% is used
        self.BMSCurrent                 = 0
        self.BMSVoltage                 = 0   # Voltage of BMS
        self.ChargerVoltage             = 0   # Voltage of Charger
        self.DisChargerVoltage          = 0   # Voltage of DisCharger
        self.ProcessCount               = 18  # only all 20 conts, mqtt sends every 2 seconds --> 40 Seconde, start with 15 to have the first read after 10seconds
        self.LastPowerArrayPosition     = 0 
        self.actchargercounter          = 100 # only change values after x METER values --> all 2 Seconds new value with chargercounter = 5 => 10seconds, first start ok -> 100
        self.waitchargercounter         = 0 

class chargerconfig:

    def iniread(self):

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
                file = logging.FileHandler(self.logpath, mode='a')
            else:
                file = logging.FileHandler(self.logpath, mode='w')
            file.setLevel(self.loglevel)
            fileformat = logging.Formatter("%(asctime)s:%(module)s:%(levelname)s:%(message)s",datefmt="%H:%M:%S")
            file.setFormatter(fileformat)
            mylogs.addHandler(file)

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
        self.CellvoltageMax            =  int(updater["Setup"]["CellvoltageMax"].value)
        self.CellvoltageMin            =  int(updater["Setup"]["CellvoltageMin"].value)
        self.CellvoltageMaxRestart     =  int(updater["Setup"]["CellvoltageMaxRestart"].value)
        self.CellvoltageMinRestart     =  int(updater["Setup"]["CellvoltageMinRestart"].value)
        self.FixedChargeVoltage        =  self.CellCount * self.CellvoltageMax
        self.StopDischargeVoltage      =  self.CellCount * self.CellvoltageMin
        self.RestartChargevoltage      =  self.CellCount * self.CellvoltageMaxRestart
        self.RestartDisChargevoltage   =  self.CellCount * self.CellvoltageMinRestart

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

        self.LastDisChargePower_delta  =  int(updater["Setup"]["LastDisChargePower_delta"].value)
        self.Voltage_ACIN_correction   =  int(updater["Setup"]["Voltage_ACIN_correction"].value)
    
        self.Selected_Device_Charger   =  int(updater["Setup"]["Selected_Device_Charger"].value)
        self.Selected_Device_DisCharger=  int(updater["Setup"]["Selected_Device_DisCharger"].value)
        self.USEDID                    =  updater["Setup"]["USEDID"].value
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

        self.Selected_LCD              =  int(updater["Setup"]["Selected_LCD"].value)
        self.lcdi2cadr                 =  int(updater["Setup"]["lcdi2cadr"].value)
    
        self.Use_GPIO                  =  int(updater["Setup"]["Use_GPIO"].value)
        self.gpio1                     =  int(updater["Setup"]["gpio1"].value)
        self.gpio2                     =  int(updater["Setup"]["gpio2"].value)
        self.gpio3                     =  int(updater["Setup"]["gpio3"].value)
        self.gpio4                     =  int(updater["Setup"]["gpio4"].value)

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

        mylogs.info("-- LCD --                   ")
        mylogs.info("Selected_LCD:               " + str(self.Selected_LCD))
        mylogs.info("lcdi2cadr:                  " + str(self.lcdi2cadr))

        mylogs.info("-- Battery parameter --     ")
        mylogs.info("CellCount:                  " + str(self.CellCount))
        mylogs.info("CellvoltageMax:             " + str(self.CellvoltageMax))
        mylogs.info("CellvoltageMin:             " + str(self.CellvoltageMin))
        mylogs.info("CellvoltageMaxRestart:      " + str(self.CellvoltageMaxRestart))
        mylogs.info("CellvoltageMinRestart:      " + str(self.CellvoltageMinRestart))

        mylogs.info("FixedChargeVoltage:         " + str(self.FixedChargeVoltage))
        mylogs.info("RestartChargevoltage:       " + str(self.RestartChargevoltage))
        mylogs.info("StopMinChargeCurrent:       " + str(self.StopMinChargeCurrent))

        mylogs.info("StopDischargeVoltage:       " + str(self.StopDischargeVoltage))
        mylogs.info("RestartDisChargevoltage:    " + str(self.RestartDisChargevoltage))
        
        mylogs.info("Read config done ...")
        return    

    def iniwrite(self):
        updater = ConfigUpdater()
        updater.read(status.configfile)

        updater["Setup"]["MW_EEPROM_COUNTER"].value = str(cfg.MW_EEPROM_COUNTER)
        updater.update_file()
        return

    def __init__(self):
      self.iniread()
      return        



def on_exit():
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
        candev.can_down()
        mylogs.info("MEANWELL EEPROM COUNTER: " + str(cfg.MW_EEPROM_COUNTER))
        cfg.iniwrite()
    
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

def handle_exit(signum, frame):
    mylogs.info("SIGNAL TO STOP RECEIVED")
    sys.exit(0)


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
            #Set_LT_Inverter(0,1)
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
        mylogs.info("-> STATUS:  C:" + str(status.ChargerEnabled) + "  D:" + str(status.DisChargerEnabled) + " | SOC:" + str(status.BMSSOC) + "%  BattV:" + str(status.BatteryVoltage/100) + "V |  Total: " + str(status.CurrentTotalWatt) + "W  Meter:" + str(status.CurrentWattValue) + "W  Average: " + str(status.CurrentAverageWatt) + "W  LastO:" + str(status.LastWattValueUsedinDevice) + "W")

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
    if (cfg.Selected_BMS == 0): return

    #Software BMS, calculate form DC Voltage, not very exact yet, almost no useable right now ;-)
    if (cfg.Selected_BMS == 1): 
          status.BMSVoltage = 0
          status.BMSCurrent = 0

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
          status.BMSSOC     = SocVal

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
          mylogs.debug ("BMS: BatVolt  : " + str(jk.voltage/100))                                                                                                    
          mylogs.debug ("BMS: Current  : " + str(jk.act_current/100))                                                                                                    
          mylogs.debug ("BMS: BMSSOC   : " + str(jk.soc))                                                                                                    
  
          status.BMSVoltage = jk.voltage
          status.BMSCurrent = jk.act_current
          status.BMSSOC     = jk.soc 
            
        except Exception as e:
            mylogs.error("JKBMS READ EXEPTION !")
            mylogs.error(str(e))
            status.BMSSOC = 0
            
        return status.BMSSOC         


#####################################################################
#Setup Operation mode of charger
def StartStopOperationCharger(val,force=0):
    mylogs.debug("StartStopOperationCharger: " + str(val))
    
    if (status.ChargerEnabled == 0):
        val = 0

    #if the Battery is not full anymore, start recharging
    if((status.BatteryFULL == 1) and (status.BatteryVoltage <= cfg.RestartChargevoltage)):
         mylogs.info("StartStopOperationCharger: Battery charging allowed again. Current Volatge: " + str(status.BatteryVoltage/100) + " (Restart Voltage: " + str(cfg.RestartChargevoltage/100) + ")")
         status.BatteryFULL = 0

    #Battery is full, stop charing and wait for discharge
    if((status.LastChargerGetCurrent != 0) and (status.LastChargerGetCurrent <= cfg.StopMinChargeCurrent)):
        status.BatteryFULL = 1

    if(status.BatteryFULL == 1):
        mylogs.info("StartStopOperationCharger: Battery Full ! - Charging current too small: " + str(status.LastChargerGetCurrent/100))
        val = 0
    
    if (force==0): #if force = 1, proceeed without any logic 
        if (status.ChargerStatus == 0) and (val == 0): 
            mylogs.debug("StartStopOperationCharger already off mode")
            return #DisCharger already off, can stop here
    
        #Check if we need to set the new value to the Charger
        p = abs(status.LastWattValueUsedinDevice - val)
    
        if (p <= cfg.LastChargePower_delta):
            mylogs.info("No change to Charger output, Delta is: " + str(p) + "  - Set to :" + str(cfg.LastChargePower_delta))
            return

    if (cfg.Selected_Device_Charger <= 1): #BIC and NPB-abc0
        #For BIC set Charge mode first
        if cfg.Selected_Device_Charger == 0: #BIC2200
            if(cfg.BICChargeDisChargeMode==1):
                mylogs.info("StartStopOperationCharger: Set BIC2200 to Charge Mode")
                candev.BIC_chargemode(0)  #set BIC to Chargemode
                BICChargeDisChargeMode=0
                cfg.MW_EEPROM_COUNTER += 1
                 
        if (MeanwellChargerSet(val,force) == True):  #try to set the new ChargeCurrent if possible
            mylogs.debug("Start Meanwell Device")
            StartStopOperationMeanwell(1)
        else: 
            mylogs.debug("Stop Meanwell Device")
            StartStopOperationMeanwell(0)     
        return     
    
    if (cfg.Selected_Device_Charger == 255):     #Simulator
        status.LastWattValueUsedinDevice = 0;  #prevent wrong calulation
        mylogs.info("Simulator Charger set to: " + str(val) + "W")
        return     

    mylogs.warning("Charger type not supported yet")
    return


def StartStopOperationDisCharger(val,force=0):
    mylogs.debug("StartStopOperationDisCharger: " + str(val))
    
    if (status.DisChargerEnabled == 0):
        mylogs.info("StartStopOperationDisCharger: DisCharger disabled !")
        val = 0

    #if the Battery is not totally empty anymore, start Discharging
    if((status.BatteryEMPTY == 1) and (status.BatteryVoltage >= cfg.RestartDisChargevoltage)):
        mylogs.info("StartStopOperationDisCharger: Battery Discharging allowed again. Current Volatge: " + str(status.BatteryVoltage/100) + " (Restart Voltage: " + str(cfg.RestartDisChargevoltage/100) + ")")
        status.BatteryEMPTY = 0

    #Battery is full, stop charing and wait for discharge
    if(status.BatteryVoltage <= cfg.StopDischargeVoltage):
        status.BatteryEMPTY = 1

    if(status.BatteryEMPTY == 1):
        mylogs.info("StartStopOperationDisCharger: Battery EMPTY ! Battery Voltage: " + str(status.BatteryVoltage/100))
        val = 0

    if (force==0): #if force = 1, proceeed without any logic 
        # Do not discharge any further if SOC is lower than specified
        if ((status.BMSSOC <= cfg.BMSminSOC) or (status.BatteryVoltage <= cfg.StopDischargeVoltage)):
            val = 0 
            mylogs.info("StartStopOperationDisCharger: SOC too low: " + str(status.BMSSOC) + "% ->  SET VALUE TO: " + str(val))

        if(status.DisChargerStatus == 0) and (val == 0): 
            mylogs.info("StartStopOperationDisCharger: Already off mode")
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
        if(cfg.BICChargeDisChargeMode==0):
            mylogs.info("StartStopOperationDisCharger: Set BIC2200 to DisCharge Mode")
            candev.BIC_chargemode(1)  #set BIC to DisChargemode
            BICChargeDisChargeMode=1
            cfg.MW_EEPROM_COUNTER += 1

        BICDisChargerSet(Newval,force)
        return     


    if (cfg.Selected_Device_DisCharger == 1): #Lumentree
        Set_LT_Inverter(Newval,force)    
        return     
    
    if (cfg.Selected_Device_DisCharger == 255): #Simulator
        mylogs.info("Simulator DisCharger set to: " + str(Newval) + "W")
        status.LastWattValueUsedinDevice = 0; #prevent wrong calulation
        return     

    mylogs.warning("DisCharger type not supported yet")
    return


#####################################################################
# Operation Meanwell
def StartStopOperationMeanwell(val):
    mylogs.debug("StartStopOperationMeanwell: " + str(val))
    
    if (val == 0):  
        if (status.ChargerStatus != 0):
            candev.operation(1,0)
            status.ChargerStatus = 0
            status.ZeroImportWatt = 0   
            mylogs.debug("Meanwell: Operation mode set to: OFF")
            cfg.MW_EEPROM_COUNTER += 1
        else:
            mylogs.debug("Meanwell: Operation mode already OFF")
    else:
        if (status.ChargerStatus != 1):
            candev.operation(1,1)   
            status.ChargerStatus = 1   
            mylogs.debug("Meanwell: Operation mode set to: ON")
            cfg.MW_EEPROM_COUNTER += 1
        else:
            mylogs.debug("Meanwell: Operation mode already ON")
    
    return val


def BICDisChargerSet(val,force=0):

    #read voltage from BIC device
    vout  = candev.v_out_read()
    
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
            c = candev.BIC_discharge_i(1,IntCurrent)
            status.LastDisChargerCurrent = IntCurrent;
            cfg.MW_EEPROM_COUNTER += 1
        else:
            mylogs.info("Meanwell BIC: Wait for next change: " + str(status.actchargercounter) + "  of: " + str(cfg.MeterUpdateCounter))
            status.actchargercounter += 1
    else:
        mylogs.info("Meanwell BIC: No New current to set. Last current: " + str(status.LastDisChargerCurrent))
        
    
    sleep(0.1)
    iout  = candev.i_out_read()
    NewVal = int((iout*vout)/10000)

    mylogs.info("Meanwell BIC: W Battery_Vout:" + str(vout/100) + ":V: Battery_I_out:" + str(iout/100) + ":A: I Calc:" + str(IntCurrent) + " = " + str(IntCurrent/100) + ":A --> WATT: " + str(NewVal))

    status.LastWattValueUsedinDevice = NewVal
    return OPStart


def MeanwellChargerSet(val,force=0):
    #StartStopOperationDisCharger(0) #has to be in the final enable/disbale function 

    #read voltage and current from NBB device
    vout  = candev.v_out_read()
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
        if (status.actchargercounter >= cfg.MeterUpdateCounter):
            mylogs.info("Meanwell: >>>> Set new current to: " + str(IntCurrent) + "  (Last current set: " + str(status.LastChargerSetCurrent) + ") <<<<")
            
            if(IntCurrent == 0):
                #Probably no need to set since device will be set to OFF mode
                #c = candev.i_out_set(1,IntCurrent)
                #cfg.MW_EEPROM_COUNTER += 1
                status.LastChargerSetCurrent = IntCurrent;
                OPStart = False #device start
            else:
                if((status.LastChargerGetCurrent < (status.LastChargerSetCurrent-100)) and (status.BMSSOC > 98)):
                    mylogs.info("Meanwell: >>>> NO SET -> BATTERY ALMOST FULL: " + str(IntCurrent) + " (Last current GET: " + str(status.LastChargerGetCurrent)  + "  (Last current SET: " + str(status.LastChargerSetCurrent) + ") <<<<")
                    OPStart = True #device start or continue
                else:
                    c = candev.i_out_set(1,IntCurrent)
                    status.LastChargerSetCurrent = IntCurrent;
                    cfg.MW_EEPROM_COUNTER += 1
                    OPStart = True #device start or continue
            status.actchargercounter = 1 #Reset counter to 1 
        else:
            mylogs.info("Meanwell: Wait for next change: " + str(status.actchargercounter) + "  of: " + str(cfg.MeterUpdateCounter))
            status.actchargercounter += 1
            if(status.ChargerStatus == 0):#do not chnage the current status
                OPStart = False
            else:
                OPStart = True             
    else:
        if(IntCurrent != 0):
            mylogs.info("Meanwell: No New current to set. Last current: " + str(status.LastChargerSetCurrent))
            OPStart = True #device start or continue
        
              
    
    sleep(0.3)
    status.LastChargerGetCurrent  = candev.i_out_read()
    NewVal = int((status.LastChargerGetCurrent*vout)/10000)
    mylogs.info("Meanwell: Battery_Vout:" + str(vout/100) + ":V: I_out:" + str(status.LastChargerGetCurrent/100) + ":A: I Calc:" + str(IntCurrent/100) + ":A - GET ACT: " + str(NewVal) + "W")
    status.LastWattValueUsedinDevice = NewVal*(-1)
    
    return OPStart



#####################################################################
#####################################################################
#####################################################################
# Operation Lumentree reopen if Device has communication errors
def ReOpen_LT():
    mylogs.warning("ReOpen Lumentree !")
    
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
def LT_Check():
    if (cfg.Selected_Device_DisCharger != 1): return

    mylogs.debug("------> Lumentree Check Alive ...")
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
def Set_LT_Inverter(val,force=0):
    mylogs.debug("Set_LT_Inverter to value: " + str(val))

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
            mylogs.debug("Set_LT_Inverter: No change to DISCharger output: " + str(status.LastWattValueUsedinDevice) + " NewWatt Value: " + str(outpower))
            return 0     #no need to set the same again, mainly for max power, delta is handled above
        else:
            mylogs.debug("Set_LT_Inverter LastWATT value: " + str(status.LastWattValueUsedinDevice) + " NewWatt Value: " + str(outpower))
    
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
                mylogs.info("LT_Inverter DC volatge too low. Probably Battery empty : " + str(DCvoltage))
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
    
    mylogs.info("SET_LT_Inverter : Outpower set to LT1: " + str(outpower1) + "   LT2: " + str(outpower2) + "   LT3: " + str(outpower3))
    if (outpower != 0):
        mylogs.info("SET_LT_Inverter : Outpower should be 0 now - check settings ! - " + str(outpower))
        
    try:
        #Lumentree Inverter 1
        mylogs.debug("Set_LT_Inverter   (1) : " + str(outpower1))
        LT1.set_watt_out(outpower1);
        sleep(0.2)  #wait 0.2 seconds to read next value
        status.LastWattValueUsedinDevice = LT1.read_watt_out()
    
        #Lumentree Inverter 2
        if (cfg.lt_count > 1):
            mylogs.debug("Set_LT_Inverter   (2) : " + str(outpower2))
            LT2.set_watt_out(outpower2);
            sleep(0.2)  #wait 0.2 seconds to read next value
            status.LastWattValueUsedinDevice = status.LastWattValueUsedinDevice + LT2.read_watt_out()
            
        #Lumentree Inverter 3
        if (cfg.lt_count > 2):
            mylogs.debug("Set_LT_Inverter   (3) : " + str(outpower3))
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
        status.DisChargerStatus = 1           #prevent not setting if LT is back again 
        ReOpen_LT()

    mylogs.info("Read_LT_Inverter Total: " + str(status.LastWattValueUsedinDevice))
    return 
    
    
def GetChargerVoltage():
    try:
        if (cfg.Selected_Device_Charger <= 1): #BIC and NPB-abc0
            status.ChargerVoltage = candev.v_out_read()

    except:
        mylogs.error("GetChargerVoltage EXEPTION !")
        mylogs.error(str(e))
    return status.ChargerVoltage


def GetDisChargerVoltage():
    try:
        if (cfg.Selected_DisDevice_Charger == 0): #BIC2200
            status.DisChargerVoltage = candev.v_out_read()
            
        if (cfg.Selected_DisDevice_Charger == 1): #Lumentree
            #status.DisChargerVoltage = LT1.readDCvoltage() * 10 #return 3 digits, need 4 for compare --> *10
            mylogs.info("GetDisChargerVoltage: Nothing to do here, this is already done in LT_Check !")

    except:
        mylogs.error("GetDisChargerVoltage EXEPTION !")
        mylogs.error(str(e))
    return status.ChargerVoltage


def GetBatteryVoltage():
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

    except:
        mylogs.error("GetBatteryVoltage EXEPTION !")
        mylogs.error(str(e))
    
    return

#####################################################################
#calculate the output power by array
#####################################################################
def getoutputpower(val):
    try:
        status.ProcessCount+=1
        if(status.ProcessCount > 20): #every 20 power value reads, if set to 2 seconds --> all 40 seconds 
            status.ProcessCount = 1
            bms_read()  #Read all data and set some status IDs
            LT_Check()  #Check every minute if LT is online, and get CD Voltage, if not try to reconnect
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
    mylogs.debug("TotalWatt: " + str(power) + "W  -  CalcAverage: " + str(status.CurrentAverageWatt) + "W")

#######################################################################################################################################
#######  Method 0 DEBUG ###############################################################################################################
#######################################################################################################################################
    if (cfg.PowerControlmethod == 0):
        mylogs.ERROR("PowerControlmethod: 0 - DO NOT USE - ONLY FOR DEBUG")

#######################################################################################################################################
#######  Method 1 Universal, Just check if positive or negative power #################################################################
#######################################################################################################################################
    if (cfg.PowerControlmethod == 1):
        mylogs.debug("PowerControlmethod: 1 - Universal mode")
        
        if (status.ZeroImportWatt > 0):      #charger take small power from Grid for charging, check if still valid
            if((NewPower - status.ZeroImportWatt) > cfg.ZeroDeltaChargerWatt):
                status.ZeroImportWatt = 0   #too much delta, reset and use normal way
            else:
                mylogs.info("ChargeMethod: 1 with ZeroImport")
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
mylogs  = logging.getLogger()
spath   = os.path.dirname(os.path.realpath(sys.argv[0]))
status.configfile = spath + "/BSsetup.conf"
cfg     = chargerconfig()

if (cfg.i_changed_my_config == 0):
    print("PLEASE SET UP YOUR DEVICE IN BSsetup.conf !!")
    print("THERE IS NO GURANTEE FOR AN ERROR FREE EXECUTION")
    print("YOU TAKE THE TOTAL RISK IF YOU USE THIS SCRIPT !!!")
    print("ONLY FOR USE WITH LIFEPO4 CELLS !!!")
    print("BATTERIES CAN BE DANGEROUS !!!")
    print("CHECK ALL PARAMETERS CAREFULLY !!!")
    sys.exit()


if((cfg.CellvoltageMax > 365) or (cfg.CellvoltageMin < 250)):
    print("CELL SET VOLTAGE TOO HIGH OR TOO LOW")
    mylogs.error("\n\nCELL VOLTAGE TOO HIGH OR TOO LOW!\n")
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
          display = i2clcd()
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
    mylogs.debug("OPEN CAN DEVICE: MEANWELL")
    candev = mwcan(cfg.Selected_Device_Charger,cfg.USEDID,"",cfg.loglevel)
    
    #Init and get get Type of device
    try:
        mwt = candev.can_up()
        mylogs.info(mwt)
    except Exception as e:
        mylogs.error("\n\nMeanwell Device not found !\n")
        mylogs.error(str(e))
        printlcd("EXEPT Meanwell",str(e))
        sys.exit(1)
    
    #print(candev.serial_read())
    mylogs.info(mwt + " temperature: " + str(candev.temp_read()/10) + " C")
    
    #get grid voltage from meanwell device
    Voltage_IN = 0
    Voltage_IN = round(float(candev.v_in_read()/10)) 
    Voltage_IN = Voltage_IN + cfg.Voltage_ACIN_correction  
    mylogs.info("Grid Voltage: " + str(Voltage_IN) + " V")
    
    #Set main parameter and stop device
    mylogs.debug("Operation STOP: " + str(candev.operation(1,0)))
    StartStopOperationCharger(0,1)

    #Set fixed charge voltage to device BIC and NPB
    rval = candev.v_out_set(1,cfg.FixedChargeVoltage)
    mylogs.info("SET CHARGE VOLTAGE: " + str(rval))
    cfg.MW_EEPROM_COUNTER += 1


    if (cfg.Selected_Device_Charger==0):
        #setup Bic2200
        #set to charge mode first
        sc  = candev.system_config(0,0)
        bic = candev.BIC_bidirectional_config(0,0)
        if (is_bit(sc,SYSTEM_CONFIG_CAN_CTRL) or is_bit(bic,0)):
            print("MEANWELL BIC2200 IS NOT IN CAN CONTROL MODE OR BI DIRECTIONAL MODE WHICH IS NEEDED !!!\n")
            c = input("SET CONTROLS NOW ? (y/n): ")
            if(c == "y"):
                sc  = candev.candev.system_config(1,set_bit(sc,0))
                bic = candev.candev.BIC_bidirectional_config(1,set_bit(bic,0))
                print("YOU HAVE TO POWER CYCLE OFF/ON THE MEANWELL BIC2200 NOW BY YOURSELF !!")
                cfg.MW_EEPROM_COUNTER += 2
            sys.exit(1) 
        
        candev.BIC_chargemode(0)
        cfg.BICChargeDisChargeMode = 0
        #set Min Discharge voltage
        candev.BIC_discharge_v(1,StopDischargeVoltage)
        
    if (cfg.Selected_Device_Charger==1):
        #setup NPB
        cuve = candev.NPB_curve_config(0,0,0) #Bit 7 should be 0
        if (is_bit(cuve,CURVE_CONFIG_CUVE)):    #Bit 7 is 1 --> Charger Mode
            print("MEANWELL NPB IS NOT IN PSU MODE WHICH IS NEEDED !!!\n")
            c = input("SET PSU MODE NOW ? (y/n): ")
            if(c == "y"):
                cuve = candev.NPB_curve_config(1,CURVE_CONFIG_CUVE,1) #Bit 7 should be 0
                print("YOU HAVE TO POWER CYCLE OFF/ON THE MEANWELL NPB NOW BY YOURSELF !!")
                cfg.MW_EEPROM_COUNTER += 1
            sys.exit(1) 
        
    if (cfg.MaxChargeCurrent > candev.dev_MaxChargeCurrent):
        mylogs.error("Config max charge current is too high ! " + str(cfg.MaxChargeCurrent))
        mylogs.error("Use max charge current from device ! " + str(candev.dev_MaxChargeCurrent))
        cfg.MaxChargeCurrent = candev.dev_MaxChargeCurrent

    if (cfg.MinChargeCurrent < candev.dev_MinChargeCurrent):
        mylogs.error("Config min charge current is too low ! " + str(cfg.MinChargeCurrent))
        mylogs.error("Use min charge current from device ! " + str(candev.dev_MinChargeCurrent))
        cfg.MinChargeCurrent = candev.dev_MinChargeCurrent

#################################################################
#################################################################
############  D I S C H A R G E R - S E C T I O N  ##############
#################################################################
#################################################################
# Lumentree / Trucki init
if ((cfg.Selected_Device_DisCharger == 1) or (cfg.lt_foreceoffonstartup == 1)):
    #Init and get get Type of device
    mylogs.info("Lumentree Init discharger ...")
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

    mylogs.info("MaxDisChargeWATT LT_calc.  :" + str(cfg.MaxDisChargeWATT))

#################################################################
# Discharge Simulator
if (cfg.Selected_Device_DisCharger == 255):
    mylogs.info("DISCHARGE Simulator used")
    


#################################################################
#################################################################
############  B M S - S E C T I O N  ############################
#################################################################
#################################################################
# BMS INIT
if (cfg.Selected_BMS != 0):
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
#################################################################
############  M A I N  - S E C T I O N  #########################
#################################################################
#################################################################
while True:
    if (cfg.GetPowerOption==1) or (cfg.GetPowerOption==255):
        schedule.run_pending()
    sleep(0.10)      #prevent high CPU usage
