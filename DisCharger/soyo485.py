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

# Controlling the Soyo 1000/1200 devices
# Not tested at all.
# Use at your own risk !  

# Version history
# macGH 30.06.2024  Version 0.1.0

import os
import logging
import serial


######################################################################################
# Explanations
######################################################################################

######################################################################################
# def __init__(self, devpath, loglevel):
#
# devpath
# Add the /dev/tty device here, mostly .../dev/ttyUSB0, if empty default path /dev/ttyUSB0 is used
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
class soyo485:

    def __init__(self, devpath, loglevel):
        #init with default
        self.devpath  = "/dev/ttyAMA0" #just try if is is the common devpath
        self.loglevel = 20             #just use info as default
        
        if devpath  != "": self.devpath    = devpath
        if loglevel != "": self.loglevel   = loglevel

        logging.basicConfig(level=loglevel, encoding='utf-8')
        logging.info("Init Soyo485 class")

    def soyo485_open(self):
        logging.debug("open serial interface")

        try:
            self.SoyoRS485 = serial.Serial(self.devpath)
        except:
            logging.error("SoyoRS485 Device not found")
            logging.error("If device is correct, check if User is in dialout group !")
            raise Exception("SoyoRS485 DEVICE NOT FOUND")
        
        self.SoyoRS485.baudrate = 115200
        self.SoyoRS485.timeout  = 0.2
        logging.debug(self.SoyoRS485)

    def soyo485_close(self):
        logging.debug("close serial interface")
        self.soyo485.close() #Shutdown our interface

    #############################################################################
    # Write operation function
    def soyo485_set_soyo_demand(self,val):	# create and send the packet for soyosource gti
        pu = val >> 8
        pl = val & 0xFF
        cs = 264 - pu - pl
        if cs > 255: 
            if val > 250:	cs -= 256
            else:			cs -= 255
        
        try:
            self.soyo485.write( bytearray([0x24,0x56,0x00,0x21,pu,pl,0x80,cs]) )
            self.soyo485.flush()
            return val
        except Exception as e:
            logging.error("Exception during write operation !")
            raise Exception(str(e))
            return 0

    #############################################################################
    # Operation function
    
    def set_watt_out(self,val):
        logging.debug("write power out: " + str(val))
        r = self.soyo485_set_soyo_demand(val) #does only return 0
        return r  #return the same value to signal OK
