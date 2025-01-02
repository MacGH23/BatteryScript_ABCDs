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

# Controlling the Huawei r48xxgx devices with CAN interface
# Please note: this Lib is currently only wokring with these 2 devices 
# and also not fully tested.
# Use at your own risk !  

# Requirement for using
# Needed external python modules
# pip3 install ifcfg

# Version history
# macGH 01.10.2024  Version 0.1.0

#missing
returnvalue format to 1024 --> x 100

import os
import can
import ifcfg
import configparser
import logging

######################################################################################
# Explanations
######################################################################################

######################################################################################
# def __init__(self, devpath, loglevel):
#
# devpath
# Add the right /dev/tty device here, mostly .../dev/ttyACM0, if empty default path is used
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


######################################################################################
# const values
#Devices


#########################################
# gereral function
def set_bit(value, bit):
    return value | (1<<bit)

def clear_bit(value, bit):
    return value & ~(1<<bit)

def is_bit(value, bit):
    return bool(value & (1<<bit))

#########################################
##class
class r48xx:
  
##################################################################################################################################################
##################################################################################################################################################

    def checkcandevice(self,val):
        f = 0
        for name, interface in ifcfg.interfaces().items():
            # Check for Can0 interface
            logging.debug("can checkcandevice: " + name + " - " + str(interface))
            if interface['device'] == val:
                f = 1
                #can0 always found if slcand with RS232CAN is used, even when deleted
                #workaround because of bug in ifcfg, check if up and running
                logging.info("Found can0 interface. Check if already up ... ")
                if(interface['flags'] == "193<UP,RUNNING,NOARP> "):  
                    f = 2
                    logging.info("Found can0 interface. Already created.")
        return f

    def __init__(self, devpath, loglevel):
        logging.basicConfig(level=loglevel, encoding='utf-8')
        if devpath == "": devpath = "/dev/ttyACM0" #just try if is is the common devpath
        self.CAN_DEVICE    = devpath

        self.USEDMWHW   = self.CAN_DEVICE 
        CAN_ADR_S       = "0x108040FE"
        CAN_ADR_S_R     = "1081407F"

        CAN_ADR_S_SET   = "0x108180FE"
        CAN_ADR_S_R_SET = "1081807E"

        self.CAN_ADR   = int(CAN_ADR_S,16)
        self.CAN_ADR_R = CAN_ADR_S_R           #need string to compare of return of CAN
      
        self.CAN_ADR_SET   = int(CAN_ADR_S_SET,16)
        self.CAN_ADR_R_SET = CAN_ADR_S_R_SET           #need string to compare of return of CAN

        logging.debug("CAN device  : " + self.CAN_DEVICE)
        logging.debug("CAN adr to  : " + str(self.CAN_ADR))
        logging.debug("CAN adr from: " + self.CAN_ADR_R)

    #########################################
    # CAN function
    def can_up(self):
        self.can0found = self.checkcandevice("can0") 
        
        if self.can0found < 2: #2 = fully up, #1 = created but not up, #0 = can0 not exists, mostly RS232 devices 
            if self.can0found == 0: 
                os.system('sudo slcand -f -s5 -o ' + self.CAN_DEVICE) #looks like a RS232 device, bring it up 
                logging.debug("can_up: RS232 DEVICE ?")

            logging.debug("can_up: Link Set")
            os.system('sudo ip link set can0 up type can bitrate 250000')
            os.system('sudo ip link set up can0 txqueuelen 1000')
        
        # init interface for using with this class
        logging.debug("can_up: init SocketCan")
        self.can0 = can.interface.Bus(channel = 'can0', bustype = 'socketcan')
        
        #Get Meanwell device and set parameter from mwcan.ini file
        t = self.type_read().strip()
        if self.mwcaniniread(t) == -1:
            raise Exception("MEANWELL DEVICE NOT FOUND")
        
        return t
        
    def can_down(self):
        self.can0.shutdown() #Shutdown our interface
        if self.can0found < 2: #only shutdown system can0 if it was created by us
            logging.info("can_down: shutdown CAN0")
            os.system('sudo ip link set can0 down')
            os.system('sudo ip link del can0')
        else:
            logging.info("can0 was externally created. Not removing it.")


    #########################################
    # receive function
    def can_receive(self):
        msgr = str(self.can0.recv(0.5))
        logging.debug(msgr)
        if msgr != "None":
            msgr_split = msgr.split()
            #Check if the CAN response is from our request
            if((msgr_split[3] != self.CAN_ADR_R) and (msgr_split[3] != self.CAN_ADR_R_SET)):
                return -1

            if(msgr_split[3] == self.CAN_ADR_R):
                #returns always 8 bytes
                if msgr_split[7] == "8":
                hexval = bytearray.fromhex(msgr_split[15]+msgr_split[14]+msgr_split[13]+msgr_split[12])
                decval = int(hexval.hex(),16)
                hexval = hexval.hex() 

                logging.debug("Return HEX: " + hexval)
                logging.debug("Return DEC: " + str(decval))
                logging.debug("Return BIN: " + format(decval, '#016b'))
            
            if(msgr_split[3] == self.CAN_ADR_R_SET):
                #returns always 1 bytes
                hexval = bytearray.fromhex(msgr_split[12])
                decval = int(hexval.hex(),16)
                hexval = hexval.hex() 

                logging.debug("Return HEX: " + hexval)
                logging.debug("Return DEC: " + str(decval))
                logging.debug("Return BIN: " + format(decval, '#016b'))

        else: 
            logging.error("ERROR: TIMEOUT - NO MESSAGE RETURNED ! CHECK SETTINGS OR MESSAGE TYPE NOT SUPPORTED !")
            decval = -1

        return decval
    
    #############################################################################
    # Read Write operation function
    def can_read_write(self,lobyte,hibyte,rw,val):
        if rw==0:#read
            msg = can.Message(arbitration_id=self.CAN_ADR, data=[lobyte,hibyte], is_extended_id=True)
            self.can0.send(msg)
            v = self.can_receive()
        else:#write
            valhighbyte = val >> 8
            vallowbyte  = val & 0xFF
            msg = can.Message(arbitration_id=self.CAN_ADR_SET, data=[lobyte,hibyte,vallowbyte,valhighbyte], is_extended_id=True)
            self.can0.send(msg)
            v = val
            
        return v
    
###############################################
##### READ function ##########################
###############################################
    
    def checkalive(self):
        logging.debug("Check alive 0x0000")
        # Command Code 0x0000
        return self.can_read_write(0x00,0x00,0,0)
    
    def checkalive1(self):
        logging.debug("Check alive 0x0103")
        # Command Code 0x010E
        return self.can_read_write(0x0E,0x01,0,0)

    def p_in_read(self):
        logging.debug("read ac power (format: value, F=x 1024)")
        # Command Code 0x0170
        return self.can_read_write(0x70,0x01,0,0)

    def freq_in_read(self):
        logging.debug("read ac voltage (format: value, F=x 1024)")
        # Command Code 0x0171
        return self.can_read_write(0x71,0x01,0,0)

    def c_in_read(self):
        logging.debug("read ac current (format: value, F=x 1024)")
        # Command Code 0x0172
        return self.can_read_write(0x72,0x01,0,0) / 1024
    
    def outpower_read(self):
        logging.debug("read output power (format: value, F=x 1024)")
        # Command Code 0x0173
        return self.can_read_write(0x73,0x01,0,0)

    def efficiency_read(self):
        logging.debug("read efficiency (format: value, F=x 1024)")
        # Command Code 0x0174
        return self.can_read_write(0x74,0x01,0,0)

    def v_out_read(self):
        logging.debug("read output voltage (format: value, F=x 1024)")
        # Command Code 0x0175
        return self.can_read_write(0x75,0x01,0,0)

    def c_out_max_read(self):
        logging.debug("read max output current (format: value, F=x 30)")
        # Command Code 0x0176
        return self.can_read_write(0x76,0x01,0,0)

    def v_in_read(self):
        logging.debug("read input voltage (format: value, F=x 1024)")
        # Command Code 0x0178
        return self.can_read_write(0x78,0x01,0,0)

    def temp_read(self):
        logging.debug("read temperature (format: value, F=x 1024)")
        # Command Code 0x017F
        return self.can_read_write(0x7F,0x01,0,0)

    def c_out1_read(self):
        logging.debug("read output current (format: value, F=x 1024)")
        # Command Code 0x0181
        return self.can_read_write(0x81,0x01,0,0)

    def c_out2_read(self): #should be the same as out1 ??
        logging.debug("read output current 2 (format: value, F=x 1024)")
        # Command Code 0x0182
        return self.can_read_write(0x82,0x01,0,0)

###############################################
##### WRITE function ##########################
###############################################

    def v_out_set_online(self,val):
        logging.debug("write charge voltage setting for online CAN mode (format: value, x 1020)")
        # Command Code 0x0100
        if val < 4150: #min valve
            val = 4150
        if val > 5850: #max value
            val = 5850
        return self.can_read_write(0x00,0x01,1,val)
   
    def v_out_set_offline(self,val):
        logging.debug("write charge voltage setting for offline CAN mode (format: value, x 1020)")
        # Command Code 0x0101
        if val < 4150: #min valve
            val = 4150
        if val > 5850: #max value
            val = 5850
        return self.can_read_write(0x01,0x01,1,val)

    def c_out_set_online(self,val):
        logging.debug("write charge current setting for online CAN mode (format: value, x 30)")
        # Command Code 0x0103
        if val < 0: #min valve
            val = 0
        if val > 6000: #max value
            val = 6000
        return self.can_read_write(0x03,0x01,1,val)
   
    def c_out_set_offline(self,val):
        logging.debug("write charge current setting for offline CAN mode (format: value, x 30)")
        # Command Code 0x0104
        if val < 0: #min valve
            val = 0
        if val > 6000: #max value
            val = 6000
        return self.can_read_write(0x04,0x01,1,val)

