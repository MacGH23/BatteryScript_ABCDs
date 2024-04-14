#Lib for constant based charger to switch on / off only
#Devid:
#0: Tasmota
#1: Shelly

import os
import sys
import logging
import requests
from time import sleep

class ChargerConstBased:

    def __init__(self, devid, ipadr, devuser, devpass, loglevel):
        logging.basicConfig(level=loglevel, encoding='utf-8')
        self.devid       = devid
        self.ipadr       = ipadr
        self.devuser     = devuser
        self.devpass     = devpass
        self.statusoffon = -1
        logging.debug("ConstBasedCharger devid   : " + str(self.devid))
        logging.debug("ConstBasedCharger ipadr   : " + self.ipadr)
        logging.debug("ConstBasedCharger devuser : " + self.devuser)
        logging.debug("ConstBasedCharger devpass : " + self.devpass)
        return

    def StatusOnOff(self):
        return self.statusoffon 

    def PowerOn(self):
        if(self.devid == 0): #Tasmota
            if(self.devuser != ""):
                requp = "user=" + self.devuser + "&password=" + self.devpass + "&"
            else:
                requp = ""
            reqstr = "http://" + self.ipadr + "/cm?" + requp + "cmnd=Power%20On"

        if(self.devid == 1): #Shelly
            if(self.devuser != ""):
                requp = self.devuser + ":" + self.devpass + "@"
            else:
                requp = ""
            reqstr = "http://" + requp + self.ipadr + "/relay/0?turn=on"


        logging.debug("ConstBasedCharger reqstr: " + reqstr)
        s = requests.get(reqstr)
        if(s.status_code == 200):
            logging.debug("ConstBasedCharger: Status ON")
            self.statusoffon = 1
            return 1
        else:
            return -1

    def PowerOff(self):
        if(self.devid == 0): #Tasmota
            if(self.devuser != ""):
                requp = "user=" + self.devuser + "&password=" + self.devpass + "&"
            else:
                requp = ""

            reqstr = "http://" + self.ipadr + "/cm?" + requp + "cmnd=Power%20Off"

        if(self.devid == 1): #Shelly
            if(self.devuser != ""):
                requp = self.devuser + ":" + self.devpass + "@"
            else:
                requp = ""
            reqstr = "http://" + requp + self.ipadr + "/relay/0?turn=off"

        logging.debug("ConstBasedCharger reqstr: " + reqstr)
        s = requests.get(reqstr)
        if(s.status_code == 200):
            logging.debug("ConstBasedCharger: Status OFF")
            self.statusoffon = 0
            return 0
        else:
            return -1
