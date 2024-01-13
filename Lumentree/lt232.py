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

# Controlling the Lumetree devices LT 600 / 1000 / 2000
# Should also work for Trucki-Platine 
# and also not fully tested.
# Use at your own risk !  

# Requirement for using
# Needed external python modules
# pip3 install minimalmodbus

# Version history
# macGH 26.11.2023  Version 0.1.0

import os
import logging
import minimalmodbus
#API https://minimalmodbus.readthedocs.io/en/stable/apiminimalmodbus.html#apiminimalmodbus

#Lumentree modbus addresses, differ from documentation ! 
#  40 = Set Watt in decimal, no reading  !
#  70 = AC Voltage    *0,1
#  94 = Temperature   *0,1
# 107 = Read Watt out *0,1
# 109 = DC Voltage    *0,1

######################################################################################
# Explanations
######################################################################################

######################################################################################
# def __init__(self, devpath, idadr, loglevel):
#
# devpath
# Add the /dev/tty device here, mostly .../dev/ttyUSB0, if empty default path /dev/ttyUSB0 is used
#
# idadr
# ID of the lumentree if you have more than one installed, if empty 1 is used
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
class lt232:

    def __init__(self, devpath, idadr, loglevel):
        #init with default
        self.devpath  = "/dev/ttyUSB0" #just try if is is the common devpath
        self.idadr    = 1              #just try if is is the common idadr
        self.loglevel = 20             #just use info as default
        
        if devpath  != "": self.devpath    = devpath
        if idadr    != "": self.idadr      = idadr
        if loglevel != "": self.loglevel   = loglevel
        
        logging.basicConfig(level=loglevel, encoding='utf-8')
        logging.info("Init lt232 class")

    def lt232_open(self):
        logging.info("open serial interface")
        try:
            self.lt232 = minimalmodbus.Instrument(self.devpath, self.idadr) # port name, slave address (in decimal)
        except Exception as e:
            logging.error("Can not init Lumentree device: " + devpath + " address: " + idadr)
            logging.error("If device is correct, check if User is in dialout group !")
            raise Exception("LUMENTREE DEVICE NOT FOUND")

        self.lt232.serial.baudrate = 9600   # Baudrate
        self.lt232.serial.timeout  = 1      # according Spec LT has a 1 Second timeout
        logging.debug(self.lt232)

    def lt232_close(self):
        logging.info("close serial interface")
        try:
            self.lt232.serial.close() #Shutdown our interface
        except Exception as e:
            logging.error("Can not close Lumentree device")
            raise Exception("LUMENTREE DEVICE CAN NOT BE CLOSED")

    #############################################################################
    # Read Write operation function
    def lt232_IO(self, regnr, wr, value):
        #Lumentree modbus addresses, differ from documentation ! 
        #  40 = Set Watt in decimal, no reading  ! Read see 107 
        #  70 = AC Voltage    *0,1
        #  94 = Temperature   *0,1
        # 107 = Read Watt out *0,1
        # 109 = DC Voltage    *0,1

        logging.debug("lt232_IO: " + str(regnr) + "-" + str(wr) + "-" + str(value))
        if wr == 0: #read
            try:
                readvalue = self.lt232.read_register(regnr)  # Registernumber (number of decimals)
            except Exception as e:
                logging.error("Exception during read operation !")
                raise Exception(str(e))
                return -1
            return readvalue
            
        if wr == 1: #write
            #40 = Set output in Watt
            try:
                self.lt232.write_register(regnr, value)  # Registernumber, value, number of decimals for storage
            except Exception as e:
                logging.error("Exception during write operation !")
                raise Exception(str(e))
                return -1
                
            return value

    
    #############################################################################
    # Operation function
    
    def set_watt_out(self,val):
        logging.debug("write power out: " + str(val))
        self.lt232_IO(40,1,val) #does only return 0
        return val  #return the same value to signal OK

    def readACvoltage(self):
        logging.debug("read AC voltage of lumentree")
        rval = self.lt232_IO(70,0,0)
        logging.debug("AC voltage of lumentree: " + str(rval/10))
        return (rval/10)

    def readtemp(self):
        logging.debug("read temperature of lumentree")
        rval = self.lt232_IO(94,0,0)
        logging.debug("Lumentree temperature: " + str(rval/10))
        return (rval/10)

    def read_watt_out(self):
        logging.debug("read power out")
        rval = self.lt232_IO(107,0,0) 
        rvali = int(rval/10)          #return without decimals
        if(rvali < 10): rvali = 0 #check if lumentree is off <15 = off
        return int(rvali)   

    def readDCvoltage(self):
        logging.debug("read AC voltage of lumentree")
        rval = self.lt232_IO(109,0,0)
        logging.debug("DC voltage of lumentree: " + str(rval))
        return int(rval)
