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
# Should also work for Trucki-Platine for Lumentree but not tested
# Should also work for TruckiRS485-Platine for SUN1000 but not tested
# and also not fully tested.
# Use at your own risk !  

# Requirement for using
# Needed external python modules
# pip3 install minimalmodbus

# Version history
# macGH 26.11.2023  Version 0.1.0
# macGH 14.04.2024  Version 0.1.1: Added Trucki RS485 via UART

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

LT_Set_Watt    =  40
LT_AC_Voltage  =  70
LT_Temperature =  94
LT_Read_Watt   = 107
LT_DC_Voltage  = 109

#[0] 	Set inverter AC output power [W*10] 	(Update rate ~100ms)
#[1] 	Read display AC output power [W*10] 	(Update rate ~1.3s)
#[2] 	Read display grid voltage [V*10]    	(Update rate ~1.3s)
#[3] 	Read display battery [V*10] 	        (Update rate ~1.3s)
#[4] 	Set / Read DAC Value; [0]=0! 	        (Update rate ~100ms)
#[5] 	=1 Start Calibration. 17 Steps 	        (10s per step)
#[6] 	Mirror of REG[0] [W*10] 	            (Update rate ~100ms) Firmware >= 1.06
#[7] 	Temperature [0..118°C] 	                (Update rate ~100ms) Firmware >= 1.06
TR_Set_Watt    = 0 
TR_AC_Voltage  = 2
TR_Temperature = 7 
TR_Read_Watt   = 1 
TR_DC_Voltage  = 3 


######################################################################################
# Explanations
######################################################################################

######################################################################################
# def __init__(self, devtype, devpath, idadr, loglevel):
#
# devtype
# 0 = Lumentree
# 1 = Trucki RS485 PCB (https://github.com/trucki-eu/RS485-Interface-for-Sun-GTIL2-1000)
#
# devpath
# Add the /dev/tty device here, mostly .../dev/ttyUSB0, if empty default path /dev/ttyUSB0 is used
#
# idadr
# ID of the lumentree/TruckiRS485 if you have more than one installed, if empty 1 is used
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

    def __init__(self, devtype, devpath, idadr, loglevel):
        #init with default
        self.devtype = devtype
        self.devpath  = "/dev/ttyUSB0" #just try if is is the common devpath
        self.idadr    = 1              #just try if is is the common idadr
        self.loglevel = 20             #just use info as default
        
        if devpath  != "": self.devpath    = devpath
        if idadr    != "": self.idadr      = idadr
        if loglevel != "": self.loglevel   = loglevel

        if(devtype == 0): #Lumentree
            self.DEV_Set_Watt    = 40 
            self.DEV_AC_Voltage  = 70
            self.DEV_Temperature = 94
            self.DEV_Read_Watt   = 107 
            self.DEV_DC_Voltage  = 109 
            
        if(devtype == 1): #Trucki RS485
            self.DEV_Set_Watt    = 0 
            self.DEV_AC_Voltage  = 2
            self.DEV_Temperature = 7
            self.DEV_Read_Watt   = 1 
            self.DEV_DC_Voltage  = 3 

        logging.basicConfig(level=loglevel, encoding='utf-8')
        logging.info("Init lt232 class")

    def lt232_open(self):
        logging.info("open serial interface")
        try:
            self.lt232 = minimalmodbus.Instrument(self.devpath, self.idadr) # port name, slave address (in decimal)
        except Exception as e:
            logging.error("Can not init Lumentree/TruckiRS485 device: " + devpath + " address: " + idadr)
            logging.error("If device is correct, check if User is in dialout group !")
            raise Exception("LUMENTREE/TRUCKIRS485 DEVICE NOT FOUND")

        self.lt232.serial.baudrate = 9600   # Baudrate
        self.lt232.serial.timeout  = 1      # according Spec LT has a 1 Second timeout
        logging.debug(self.lt232)

    def lt232_close(self):
        logging.info("close serial interface")
        try:
            self.lt232.serial.close() #Shutdown our interface
        except Exception as e:
            logging.error("Can not close Lumentree/TruckiRs485 device")
            raise Exception("LUMENTREE/TRUCKIRS485 DEVICE CAN NOT BE CLOSED")

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
        if(self.devtype == 1): #Trucki RS485
            val = val*10
        self.lt232_IO(self.DEV_Set_Watt,1,val) #does only return 0
        return val  #return the same value to signal OK

    def readACvoltage(self):
        logging.debug("read AC voltage of lumentree/TruckiRS485")
        rval = self.lt232_IO(self.DEV_AC_Voltage,0,0)
        logging.debug("AC voltage of lumentree/TruckiRS485: " + str(rval/10))
        return (rval/10)

    def readtemp(self):
        logging.debug("read temperature of lumentree/TruckiRS485")
        rval = self.lt232_IO(self.DEV_Temperature,0,0)
        logging.debug("Lumentree/TruckiRS485 temperature: " + str(rval/10))
        return (rval/10)

    def read_watt_out(self):
        logging.debug("read power out")
        rval = self.lt232_IO(self.DEV_Read_Watt,0,0) 
        rvali = int(rval/10)          #return without decimals
        if(rvali < 10): rvali = 0 #check if lumentree/TruckiRS485 is off <15 = off
        return int(rvali)   

    def readDCvoltage(self):
        logging.debug("read AC voltage of lumentree/TruckiRS485")
        rval = self.lt232_IO(self.DEV_DC_Voltage,0,0)
        logging.debug("DC voltage of lumentree/TruckiRS485: " + str(rval))
        #return without /10 to have the decimals
        return int(rval)
