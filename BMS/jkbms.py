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

# Reading JKBMS
# Used https://github.com/fah/jk-bms example script and make a class
# The hex string composing the command, including CRC check etc.
# See also:
# - https://github.com/syssi/esphome-jk-bms
# - https://github.com/NEEY-electronic/JK/tree/JK-BMS
# - https://github.com/Louisvdw/dbus-serialbattery
# Only tested with 
# - B2A8S20P
# and the original RS485 adapter ! 
# Use at your own risk !  
#
# The return is a list of data.
# Depending on the cellcount, the list is longer or shorter
# Check first item for cellcount !
# Cellcount: Nr                                                                                                    
# CellVolt1 to CellVolt[nr] in *1000 notation -> 3200 = 3,2V
# ....                                                                                                    
# Temp_Fet in°C                                                                                                   
# Temp_1   in°C                                                                                                   
# temp_2   in°C                                                                                                   
# BatVolt in *100 notation -> 2380 = 23,80V                                                                                                    
# Current in *100 notation -> 1300 = 13,00A; positive = DisCharge current, negative = Charge current 
# SOC     in % (0..100)                                                                                                         
#
# Version history
# macGH 13.01.2024  Version 0.1.0

import os
import sys
import logging
import time
import struct
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
class jkbms:

    def __init__(self, devpath, loglevel):
        #init with default
        self.devpath  = "/dev/ttyUSB0" #just try if is is the common devpath
        self.loglevel = 20             #just use info as default
        
        if devpath  != "": self.devpath    = devpath
        if loglevel != "": self.loglevel   = loglevel
        
        logging.basicConfig(level=loglevel, encoding='utf-8')
        logging.debug("Init jkbms class")
        self.cells = [0]*24


    def sendBMSCommand(self, cmd_string):
        logging.debug("jkbms Send command")
        cmd_bytes = bytearray.fromhex(cmd_string)
        for cmd_byte in cmd_bytes:
            hex_byte = ("{0:02x}".format(cmd_byte))
            self.jkbms.write(bytearray.fromhex(hex_byte))
        return

    def jkbms_open(self):
        logging.debug("open serial interface")

        try:
            self.jkbms = serial.Serial(self.devpath)
        except:
            logging.error("jkbms Device not found")
            logging.error("If device is correct, check if User is in dialout group !")
            raise Exception("JKBMS DEVICE NOT FOUND")
        
        self.jkbms.baudrate = 115200
        self.jkbms.timeout  = 0.2
        logging.debug(self.jkbms)

    def jkbms_close(self):
        logging.debug("close serial interface")
        self.jkbms.close() #Shutdown our interface

    #############################################################################
    # Read Write operation function
    def jkbms_read(self):
        Status = []
        try:
            # Read all command
            logging.debug("Reading BMS")
            self.sendBMSCommand('4E 57 00 13 00 00 00 00 06 03 00 00 00 00 00 00 68 00 00 01 29')
    
            time.sleep(0.1)
    
            logging.debug("Analyse BMS")
            if self.jkbms.inWaiting() >= 4 :
                if self.jkbms.read(1).hex() == '4e' : # header byte 1
                    if self.jkbms.read(1).hex() == '57' : # header byte 2
                        # next two bytes is the length of the data package, including the two length bytes
                        length = int.from_bytes(self.jkbms.read(2),byteorder='big')
                        length -= 2 # Remaining after length bytes
    
                        # Lets wait until all the data that should be there, really is present.
                        # If not, something went wrong. Flush and exit
                        available = self.jkbms.inWaiting()
                        if available != length :
                            time.sleep(0.1)
                            available = self.jkbms.inWaiting()
                            # if it's not here by now, exit
                            if available != length :
                                self.jkbms.reset_input_buffer()
                                raise Exception("Something went wrong reading the data...")
                                                                                                                                                            
                        # Reconstruct the header and length field                                                               
                        b = bytearray.fromhex("4e57")                                                                           
                        b += (length+2).to_bytes(2, byteorder='big')                                                            
                                                                                                                                
                        # Read all the data                                                                                     
                        data = bytearray(self.jkbms.read(available))                                                                   
                        # And re-attach the header (needed for CRC calculation)                                                 
                        data = b + data                                                                                         
                                                                                                                                
                        # Calculate the CRC sum                                                                                 
                        crc_calc = sum(data[0:-4])                                                                              
                        # Extract the CRC value from the data                                                                   
                        crc_lo = struct.unpack_from('>H', data[-2:])[0]                                                         
                                                                                                                                
                        # Exit if CRC doesn't match                                                                             
                        if crc_calc != crc_lo :                                                                                 
                            jkbms.reset_input_buffer()                                                                            
                            raise Exception("CRC Wrong")                                                                        
                                                                                                                                
                        # The actual data we need                                                                               
                        data = data[11:length-19] # at location 0 we have 0x79                                                  
                                                                                                                                
                        # The byte at location 1 is the length count for the cell data bytes                                    
                        # Each cell has 3 bytes representing the voltage per cell in mV                                         
                        bytecount = data[1]                                                                                     
                                                                                                                                
                        # We can use this number to determine the total amount of cells we have                                 
                        cellcount = int(bytecount/3)                                                                            
                        Status.append(cellcount)    
                        self.cell_count = cellcount                                                                                                    
                        
                        # Voltages start at index 2, in groups of 3                                                             
                        #Voltages in 1000 -> 3590 = 3.590V
                        for i in range(cellcount) :                                                                             
                            voltage = struct.unpack_from('>xH', data, i * 3 + 2)[0]                                        
                            Status.append(voltage)
                            self.cells[i] = voltage                                                                                                        
                                                                            
                        # Temperatures are in the next nine bytes (MOSFET, Probe 1 and Probe 2), register id + two bytes each fo
                        # Anything over 100 is negative, so 110 == -10                                                          
                        temp_fet = struct.unpack_from('>H', data, bytecount + 3)[0]                                             
                        if temp_fet > 100 :                                                                                     
                            temp_fet = -(temp_fet - 100)                                                                        
                        temp_1 = struct.unpack_from('>H', data, bytecount + 6)[0]                                               
                        if temp_1 > 100 :                                                                                       
                            temp_1 = -(temp_1 - 100)                                                                            
                        temp_2 = struct.unpack_from('>H', data, bytecount + 9)[0]                                               
                        if temp_2 > 100 :                                                                                       
                            temp_2 = -(temp_2 - 100)                                                                            
                                                                                                                                
                        Status.append(temp_fet)                                                                                                        
                        Status.append(temp_1)                                                                                                        
                        Status.append(temp_2)              
                        self.temp_fet = temp_fet                                                                                            
                        self.temp_1 = temp_1                                                                                            
                        self.temp_2 = temp_2                                                                                            
                                                                                                                                
                        # Battery voltage in 100 -> 25,81 = 2581                                                                                       
                        voltage = struct.unpack_from('>H', data, bytecount + 12)[0]                                         
                        Status.append(voltage)     
                        self.voltage = voltage                                                                                                   
                                                                                                                                
                        # Current in 100 -> 9,4A = 940; + = charge; - = discharge                                                                                               
                        current = struct.unpack_from('>H', data, bytecount + 15)[0]
                        if(current > 0x8000): current = current - 0x8000
                        else: current = - current                                         
                        Status.append(current)
                        self.act_current = current                                                                                                        
                                                                                                                                
                        # Remaining capacity, %                                                                                 
                        capacity = struct.unpack_from('>B', data, bytecount + 18)[0]                                            
                        Status.append(capacity)
                        self.soc = capacity 
                                                                                                                                
                        # tempsensorcount                                                                               
#                        tempsensorcount = struct.unpack_from('>B', data, bytecount + 20)[0]                                            
#                        Status.append(tempsensorcount)

                        # cyclecount                                                                               
#                        cyclecount = struct.unpack_from('>B', data, bytecount + 22)[0]                                            
#                        Status.append(cyclecount)

            self.jkbms.reset_input_buffer()                                                                                            
                                                                                                                                
        except Exception as e :                                                                                                 
            logging.error("Error during reading jkbms")
            logging.error(str(e))

        return Status
