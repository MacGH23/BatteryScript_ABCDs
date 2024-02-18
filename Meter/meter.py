############################################################################
#    Copyright (C) 2023 by macGH                                           #
#                                                                          #
#    This lib is free software; you can redistribute it and/or modify      #
#    it under the terms of the LGPL                                        #
#    This program is distributed in the hope that it will be useful,       #
#    but WITHOUT ANY WARRANTY; without even the implied warranty of        #
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         #
#    GNU General Public License for more details.                          #
#                                                                          #
############################################################################

# Reading diffrent WATT Meter 
# Use at your own risk !  

#Credits:
# Functions are reused from
# https://github.com/reserve85/HoymilesZeroExport

# Version history
# macGH 18.12.2023  Version 0.1.0

import os
import logging
import requests
from requests.auth import HTTPBasicAuth
from requests.auth import HTTPDigestAuth

######################################################################################
# Explanations
######################################################################################

######################################################################################
# def __init__(self, meter, ip, port, user, password, vzl_uuid, emlog, iobrogerobject, loglevel):
#
#
# idadr
# ip             of the Meter you have installed
# port           of the Meter you have installed
# user           Username for login
# password       Password for login
# vzl_uuid       UUID of VZlogger,  use "" if not used
# emlog          Index of EMLogger, use "" if not used
# iobrogerobject IOBroker object string to read
#
# loglevel
# Enter Loglevel 0,10,20,30,40,50 
# CRITICAL   50
# ERROR      40
# WARNING    30
# INFO       20
# DEBUG      10
# NOTSET      0
######################################################################################

#########################################
##class
class meter:

    def __init__(self, meter, ip, port, user, password, vzl_uuid, emlog, iobrogerobject, loglevel):
        #init with default
        logging.basicConfig(level=loglevel, encoding='utf-8')
        logging.info("Init meter class")

        try:
            self.meter    = meter
            self.ip       = ip
            self.port     = port
            self.user     = user
            self.password = password
            self.loglevel = loglevel           #just use info as default
            self.VZL_UUID = vzl_uuid
            self.EMLOG_METERINDEX = emlog
            self.iobrogerobject   = iobrogerobject
        except Exception as e:
            logging.error("INIT METER CLASS EXCEPTION !")
            logging.error(str(e))
            raise Exception("INIT METER CLASS EXCEPTION !")

    def GetPowermeterWatts(self):
      try:
          if self.meter == 1: #USE_SHELLY_EM:
              return self.GetPowermeterWattsShellyEM()
          if self.meter == 2: #USE_SHELLY_3EM:
              return self.GetPowermeterWattsShelly3EM()
          if self.meter == 3: #USE_SHELLY_3EMPRO:
              return self.GetPowermeterWattsShelly3EMPro()
          if self.meter == 4: #USE_TASMOTA:
              return self.GetPowermeterWattsTasmota()
          if self.meter == 5: #USE_SHRDZM:
              return self.GetPowermeterWattsShrdzm()
          if self.meter == 6: #USE_EMLOG:
              return self.GetPowermeterWattsEmlog()
          if self.meter == 7: #USE_IOBROKER:
              return self.GetPowermeterWattsIobroker()
          if self.meter == 8: #USE_HOMEASSISTANT:
              return self.GetPowermeterWattsHomeAssistant()
          if self.meter == 9: #USE_VZLOGGER:
              return self.GetPowermeterWattsVZLogger()
          else:
              raise Exception("Error: no powermeter defined!")
      except:
          logging.error("Exception at GetPowermeterWatts")
          raise


    #############################################################################
    # Operation function
    def CastToInt(self, pValueToCast):
        try:
            result = int(pValueToCast)
            return result
        except:
            result = 0
        try:
            result = int(float(pValueToCast))
            return result
        except:
            logging.error("Exception at CastToInt")
            raise
    
    def GetPowermeterWattsTasmota(self):
        url = f'http://{self.ip}/cm?cmnd=status%2010'
        ParsedData = requests.get(url, timeout=10).json()
        logging.debug(ParsedData)
        powerz1    = (ParsedData['StatusSNS'])
        powerz2    = (powerz1['ENERGY'])
        Watts      = (powerz2['Power'])

#        if not TASMOTA_JSON_POWER_CALCULATE:
#            Watts = CastToInt(ParsedData[TASMOTA_JSON_STATUS][TASMOTA_JSON_PAYLOAD_MQTT_PREFIX][TASMOTA_JSON_POWER_MQTT_LABEL])
#        else:
#            input = ParsedData[TASMOTA_JSON_STATUS][TASMOTA_JSON_PAYLOAD_MQTT_PREFIX][TASMOTA_JSON_POWER_INPUT_MQTT_LABEL]
#            ouput = ParsedData[TASMOTA_JSON_STATUS][TASMOTA_JSON_PAYLOAD_MQTT_PREFIX][TASMOTA_JSON_POWER_OUTPUT_MQTT_LABEL]
#            Watts = CastToInt(input - ouput)
        logging.debug("METER: powermeter Tasmota: %s %s",Watts," Watt")
        return self.CastToInt(Watts)
    
    def GetPowermeterWattsShellyEM(self):
        url = f'http://{self.ip}/status'
        headers = {"content-type": "application/json"}
        ParsedData = requests.get(url, headers=headers, auth=(self.user, self.password), timeout=10).json()
        logging.debug(ParsedData)
        Watts = sum(self.CastToInt(emeter['power']) for emeter in ParsedData['emeters'])
        logging.debug("METER: powermeter Shelly EM: %s %s",Watts," Watt")
        return self.CastToInt(Watts)
    
    def GetPowermeterWattsShelly3EM(self):
        url = f'http://{self.ip}/status'
        headers = {"content-type": "application/json"}
        ParsedData = requests.get(url, headers=headers, auth=(self.user, self.password), timeout=10).json()
        logging.debug(ParsedData)
        Watts = self.CastToInt(ParsedData['total_power'])
        logging.debug("METER: powermeter Shelly 3EM: %s %s",Watts," Watt")
        return self.CastToInt(Watts)
    
    def GetPowermeterWattsShelly3EMPro(self):
        url = f'http://{self.ip}/rpc/EM.GetStatus?id=0'
        headers = {"content-type": "application/json"}
        ParsedData = requests.get(url, headers=headers, auth=HTTPDigestAuth(self.user, self.password), timeout=10).json()
        logging.debug(ParsedData)
        Watts = self.CastToInt(ParsedData['total_act_power'])
        logging.debug("METER: powermeter Shelly 3EM Pro: %s %s",Watts," Watt")
        return self.CastToInt(Watts)
    
    def GetPowermeterWattsShrdzm(self):
        url = f'http://{self.ip}/getLastData?user={self.user}&password={self.password}'
        ParsedData = requests.get(url, timeout=10).json()
        logging.debug(ParsedData)
        Watts = self.CastToInt(CastToInt(ParsedData['1.7.0']) - CastToInt(ParsedData['2.7.0']))
        logging.debug("METER: powermeter SHRDZM: %s %s",Watts," Watt")
        return self.CastToInt(Watts)
    
    def GetPowermeterWattsEmlog(self):
        url = f'http://{self.ip}/pages/getinformation.php?heute&meterindex={self.EMLOG_METERINDEX}'
        ParsedData = requests.get(url, timeout=10).json()
        logging.debug(ParsedData)
        Watts = self.CastToInt(CastToInt(ParsedData['Leistung170']) - CastToInt(ParsedData['Leistung270']))
        logging.debug("METER: powermeter EMLOG: %s %s",Watts," Watt")
        return self.CastToInt(Watts)

    def GetPowermeterWattsVZLogger(self):
        url = f"http://{self.ip}:{self.port}/{self.VZL_UUID}"
        ParsedData = requests.get(url, timeout=10).json()
        logging.debug(ParsedData)
        Watts = self.CastToInt(ParsedData['data'][0]['tuples'][0][1])
        logging.debug("METER: powermeter VZLogger: %s %s",Watts," Watt")
        return self.CastToInt(Watts)
    
    #Use Simple API of IOBroker to get the power value, install if you want to use, default port=8087
    def GetPowermeterWattsIobroker(self):
        url = f'http://{self.ip}:{self.port}/getPlainValue/{self.iobrogerobject}'
        ParsedData = requests.get(url, timeout=10)
        logging.debug(ParsedData)
        Watts = self.CastToInt(ParsedData.text)
        logging.debug("METER: powermeter IOBROKER: %s %s",Watts," Watt")
        return self.CastToInt(Watts)
"""    
    def GetPowermeterWattsHomeAssistant(self):
        if not HA_POWER_CALCULATE:
            url = f"http://{self.ip}:{self.port}/api/states/{HA_CURRENT_POWER_ENTITY}"
            headers = {"Authorization": "Bearer " + HA_ACCESSTOKEN, "content-type": "application/json"}
            ParsedData = requests.get(url, headers=headers, timeout=10).json()
            Watts = CastToInt(ParsedData['state'])
        else:
            url = f"http://{self.ip}:{self.port}/api/states/{HA_POWER_INPUT_ALIAS}"
            headers = {"Authorization": "Bearer " + HA_ACCESSTOKEN, "content-type": "application/json"}
            ParsedData = requests.get(url, headers=headers, timeout=10).json()
            input = CastToInt(ParsedData['state'])
            url = f"http://{self.ip}:{self.port}/api/states/{HA_POWER_OUTPUT_ALIAS}"
            headers = {"Authorization": "Bearer " + HA_ACCESSTOKEN, "content-type": "application/json"}
            ParsedData = requests.get(url, headers=headers, timeout=10).json()
            output = CastToInt(ParsedData['state'])
            Watts = CastToInt(input - output)
        logging.info("METER: powermeter HomeAssistant: %s %s",Watts," Watt")
        return CastToInt(Watts)
"""    

