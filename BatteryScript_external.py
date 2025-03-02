#Lib for external functions for own changes
#User can do someting for his own setup, init something else, ....
#                     WARNING
# WARNING you should really !!! know what you are doing !
#                     WARNING
######################################################
# THERE IS NO GURANTEE FOR AN ERROR FREE EXECUTION   #
# YOU TAKE THE TOTAL RISK IF YOU USE THIS SCRIPT !!! #
# ONLY FOR USE WITH LIFEPO4 CELLS !!!                #
# BATTERIES CAN BE DANGEROUS !!!                     #
# BE SURE YOU KNOW WHAT YOU ARE DOING !!             #
# THE AUTHOR(S) IS NOT LIABLE FOR ANY DAMAGE !!      #
# YOU HAVE BEEN WARNED !                             #
######################################################

import os
import sys
import logging
from time import sleep

class BatteryScript_external:

    def __init__(self, loglevel):
        logging.basicConfig(level=loglevel, encoding='utf-8')
        logging.debug("BatteryScript_external Init")
        self.devfound = 0
        return

    def ex_gpio1(self, dev, cfg, status):
        #Disable / Enbale Discharger test can be removed
        logging.info("BatteryScript_external_GPIO1 - Disable Discharger")
        if(status.DisChargerEnabled==1):
            status.DisChargerEnabled = 0
        else:
            status.DisChargerEnabled = 1
        return status

    def ext_gpio2(self, dev, cfg, status):
        logging.info("BatteryScript_external_GPIO2 - ")
        return status

    def ext_gpio3(self, dev, cfg, status):
        logging.info("BatteryScript_external_GPIO3 - ")
        return status

    def ext_gpio4(self, dev, cfg, status):
        logging.info("BatteryScript_external_GPIO4 - ")
        return status

    def ext_action_1(self, dev, cfg, status):
        logging.info("BatteryScript_external_1 - ")
        return status

    def ext_action_2(self, dev, cfg, status):
        logging.info("BatteryScript_external_2 - ")
        return status

    def ext_action_3(self, dev, cfg, status):
        logging.info("BatteryScript_external_3 - ")
        return status

    def ext_action_4(self, dev, cfg, status):
        logging.info("BatteryScript_external_4 - ")
        return status

    def ext_charger_set(self, val, force, dev, cfg, status):
        logging.debug("BatteryScript_external_charger_set - ")
        if(self.devfound == 0):
            logging.debug("BatteryScript_external_charger_set - No device found")
            return status
        return status

    def ext_discharger_set(self, val, force,  dev, cfg, status):
        logging.debug("BatteryScript_external_ex_discharger_set - ")
        if(self.devfound == 0):
            logging.debug("BatteryScript_external_discharger_set - No device found")
            return status
        return status

    def ext_close(self, dev, cfg, status):
        logging.info("BatteryScript_external_close")
        if(self.devfound == 0):
            logging.info("BatteryScript_external_close - No device found")
            return status
        return status

    def ext_open(self, dev, cfg, status):
        logging.info("BatteryScript_external_open - ")
		#do somwthing here, if you add a new device for charge/discharge set devfound = 1
        self.devfound = 0
        return status
