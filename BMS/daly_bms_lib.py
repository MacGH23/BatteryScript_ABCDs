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

# Reading DalyBMS via 
# https://github.com/dreadnought/python-daly-bms class
# Only tested with 
# - R25T*
# and the original UART adapter from Daly! 
# Use at your own risk !  
#
# The return is a list of data.
# Depending on the cellcount, the list is longer or shorter
# Check first item for cellcount !
# Cellcount: Nr                                                                                                    
# CellVolt1 to CellVolt[nr] in *1000 notation -> 3200 = 3,2V
# ....                                                                                                    
# Temp_Fet in�C                                                                                                   
# Temp_1   in�C                                                                                                   
# temp_2   in�C                                                                                                   
# BatVolt in *100 notation -> 2380 = 23,80V                                                                                                    
# Current in *100 notation -> 1300 = 13,00A; positive = DisCharge current, negative = Charge current 
# SOC     in % (0..100)                                                                                                         
#
# Version history
# macGH 26.07.2024  Version 0.1.0

import os
import sys
import logging
import time
import struct
import json

#p = os.path.dirname(os.path.abspath(__file__))
#sys.path.insert(1, p + '/dalybms')  # the type of path is string
#print(sys.path)
#from dalybms import DalyBMS
#from dalybms import DalyBMSSinowealth
from dalybms.daly_bms import DalyBMS
from dalybms.daly_sinowealth import DalyBMSSinowealth

######################################################################################
# Explanations
######################################################################################

######################################################################################
# def __init__(self, devpath, sinowealth, loglevel):
#
# devpath
# Add the /dev/tty device here, mostly .../dev/ttyUSB0, if empty default path /dev/ttyUSB0 is used
#
# sinowealth
# 0: not used
# 1: Use sinowealth
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
class dalybmslib:

    def __init__(self, devpath, sinowealth, loglevel):
        #init with default
        self.devpath    = "/dev/ttyUSB0" #just try if is is the common devpath
        self.sinowealth = 0              #just use info as default
        self.loglevel   = 20             #just use info as default
        self.address    = 4              #USB = 4 

        if devpath     != "": self.devpath    = devpath
        if sinowealth  != "": self.sinowealth = sinowealth
        if loglevel    != "": self.loglevel   = loglevel
        
        logging.basicConfig(level=loglevel, encoding='utf-8')
        logging.debug("Init daly bms class")
        self.cells = [0]*24


    def dalybms_open(self):
        logging.debug("open serial interface")

        try:
            if (self.sinowealth == 1):
                self.bms = DalyBMSSinowealth(request_retries=3, logger=logging)
            else:
                self.bms = DalyBMS(request_retries=3, address=self.address, logger=logging)
            self.bms.connect(device=self.devpath)
        except:
            logging.error("daly bms Device not found")
            logging.error("If device is correct, check if User is in dialout group !")
            raise Exception("daly bms DEVICE NOT FOUND")
        
        logging.debug(self.bms)

    def dalybms_close(self):
        logging.debug("Close daly bms serial interface")
        self.bms.disconnect()

    #############################################################################
    # Read Write operation function
    def dalybms_read(self):
        Status = []
        try:
            # Read all command
            logging.debug("Reading Daly BMS")
            dalystatus = self.bms.get_all()
            logging.debug(dalystatus)
            
            # We can use this number to determine the total amount of cells we have                                 
            cellcount = dalystatus['status']['cells']
            Status.append(cellcount)    
            self.cell_count = cellcount                                                                                                    
            
            # Voltages start at index 2, in groups of 3                                                             
            #Voltages in 1000 -> 3590 = 3.590V
            for i in range(cellcount) :                                                                             
                voltage = int(dalystatus['cell_voltages'][i+1] * 1000)
                Status.append(voltage)
                self.cells[i] = voltage                                                                                                        
                                                                
            # Temperatures are in the next nine bytes (MOSFET, Probe 1 and Probe 2), register id + two bytes each fo
            # Anything over 100 is negative, so 110 == -10                                                          
            temp_fet = -1
            temp_1   = dalystatus['temperatures'][1]                                            
            temp_2   = -1
                                                                                                                    
            Status.append(temp_fet)                                                                                                        
            Status.append(temp_1)                                                                                                        
            Status.append(temp_2)              
            self.temp_fet = -1
            self.temp_1   = temp_1                                                                                            
            self.temp_2   = temp_2                                                                                            
                                                                                                                    
            # Battery voltage in 100 -> 25,81 = 2581                                                                                       
            voltage = dalystatus['soc']['total_voltage']*100
            Status.append(voltage)     
            self.voltage = voltage                                                                                                   
                                                                                                                    
            # Current in 100 -> 9,4A = 940; + = charge; - = discharge                                                                                               
            current = dalystatus['soc']['current']*100
            Status.append(current)
            self.act_current = current                                                                                                        
                                                                                                                    
            # Remaining capacity, %                                                                                 
            capacity = int(dalystatus['soc']['soc_percent'])
            Status.append(capacity)
            self.soc = capacity 
                                                                                                                                
                                                                                                                                
        except Exception as e :                                                                                                 
            logging.error("Error during reading dalybms")
            logging.error(str(e))

        return Status
