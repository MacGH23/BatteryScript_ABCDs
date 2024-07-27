# ABCDS: *A*utomatic (DIY) *B*attery *C*harge / *D*ischarge *S*cript

Python3 script for fully automatic charge and discharge a DIY battery for photovoltaic systems to provide a "zero feed-in".<br><br>
**WARNING - USE THIS SCRIPT TOTALLY ON YOUR OWN RISK !!! (needed to add ;-)** 
**Check which device can be used in your country and fullfill all regulatory requirements !<br><br>** 
The idea of this script is to provide a framework for handling the power stuff, <br> 
and everyone can add new devices and provide it to the community.<br><br>
Current tested/running on a Raspberry Pi:
- Raspberry Pi Zero
- Raspberry Pi 2<br>

Should work on any Raspberry Pi. <br>

**Status Webserver:<br>**
For a better overview a own webserver at port 9000 is available (can be configured in conf file).<br>
Here you can have a quick overview of the current status, current config and BMS. <br> You can also enable and disable Charger and DisCharger<br>
For automation you can call a restart (see below BSstart.py) via URL:<br>
`[IP:PORT]/DIRECTRESTART[x] `<br>
x = 0..3

**Current supported hardware:<br>**
**Charger:**
* Meanwell BIC-2200
* Meanwell NPB-[450/750/1200/1700]-[12/24/48/96] incl. voltage adjust for Chargecurrent < MinCurrent (able to charge below MinCurrent)
* Constant current based power supply via external power switch <br> IP based power switch supported now: Tasmota, Shelly
* Simulator, can be used for testing

*Important Note for Meanwell devices !<br>*
Changing the output values are limited to 4.000.000 by design.<br>
The NPB has a newer firmware with an additional option to disable the EEPROM write (from 02/2024 - option will be set if available)<br>
This can only be updated by Meanwell ! <br>
Therefore several options are available to configure.<br>
- ZeroDeltaChargerWatt       =    30 (range in WATT without set device to new value)
- chargercounter = 8 (wait for change, multiply with METER updates in seconds.)<br>
e.g. (Meter update all 2 seconds) x (8) = only after 16 seconds an update will be send if necessary<br>

*Note for Meanwell NPB:*<br>
Voltage adjust is avaiable for NPB devices. This will lower the charge voltage to lower the charge current if the charge current is smaller than min charge current.<br>
It is not 100% exact, because the voltage <-> current is not exact, but you are able to charge.<br>

*Note for all Meanwell EEPROM*<br>
If EEPROM write is disabled the values which are written before disabling will be used by system start<br>
If you want to change the "default" you have to enable write EEPROM again and change it with mycancmd.py in "/charger" folder e.g. <br>
 `./mwcancmd.py.py systemconfigset 1`<br>
 `./mwcancmd.py.py cvset 2760`<br>
  `./mwcancmd.py.py dvset 2440`<br>
 `./mwcancmd.py.py systemconfigset 1025`<br>


**Discharger:**
* Meanwell BIC-2200<br>
* Lumentree (by ask4it) 600/1000/2000, upto 3 can be used in parallel<br>
* Sun1000/2000 inverters with TruckiRS485 PCB should also work with UART and RS485, but not tested <br>
* Simulator, can be used for testing

**BMS:**
* JKBMS with original JK RS485 interface adapter
* DalyBMS with original Daly UART interface adapter (no Bluetooth)

**Power meter information:<br>**
To adjust everything automatically, you need to get the current power.<br>
Positive = Take power from the GRID<br>
Negative = Get power from PV<br>
* MQTT (get vlaues from any mqtt broker)
* Shelly (EM, 3EM, 3EMPro, 1PM, 1PMPro)
* Tasmota
* IOBroker via simple REST API (install the "RESTful API" adapter)
* EMLOG (not tested)
* VZlogger (not tested)
* AMIsLeser (not tested - https://www.mitterbaur.at/amis-leser.html)
* Simulator, can be used for testing (random power value)<br>


Additional hardware needed, depending on the used hardware

Device / HW | Interface | Recommended
---|---|---|
Meanwell | CAN | [Waveshare RS485 CAN HAT](https://www.waveshare.com/rs485-can-hat.htm) or [Fischl USBTin](https://www.fischl.de/usbtin/)<br> ![Waveshare RS485CAN](/pictures/wavesharers485can.jpg "Waveshare RS485CAN")   ![Fischl USBTin](/pictures/usbtin.jpg "Fischl USBTin")
Lumentree | RS232 | Any simple USB to RS232 adapter<br> ![USB RS232](/pictures/usbrs232.jpg "USB RS232") or ![USB RS232](/pictures/RS232_USB2.jpg "USB RS232") <br> See Lumentree installation hints 
JKBMS | RS485 | [Waveshare RS485 CAN HAT](https://www.waveshare.com/rs485-can-hat.htm) with original JKRS485 adapter<br> ![JKBms RS485](/pictures/jkbms_rs485.jpg "JKBms RS485")
DALYBMS | UART | Original DALY UART USB adapter<br> ![DALYBms UART RS485](/pictures/dalybms_uart.jpg "JKBms RS485")


Meanwell devices using a small 2x7 pin, 2.0 pitch connector from MPE for the CAN interface.<br> Normally a connector with 2 wires are part of the delievery. The connector is a [MPE BLC 14](https://www.reichelt.de/crimp-buchsenleiste-14-pol-mpe-blc-14-p247189.html?CCOUNTRY=445&LANGUAGE=de&nbc=1&&r=1) (partnumber 906-2-014-X-BS0A10) and [crimp pins](https://www.reichelt.de/crimpkontakt-fuer-mpe-blc-einzeln-mpe-cc222-p150922.html?CCOUNTRY=445&LANGUAGE=de&nbc=1&&r=1) (partnumber CC2-22/30-TT-RL)

Only the CAN wires are needed to install additionally. See manual of the device where the CAN PINs are.

Lumentree devices uses a normal RS232 interface with modbus protocol.<br>
Easiest methode to connect is a simple USB to RS232 adapter.<br>
But see also Lumentree installation hints, because of Pin 9! <br>

JKBMS is optional. You have to use the original JK RS485 adapter and connect it to a RS485 interface at the Raspberry. <br>
Use the Waveshare CAN/RS485 HAT. Especially if you also use a CAN device.

MQTT publish:<br>
You can publish some data form the script to the mqtt server.<br>
Change the already implemented ones in the charger.conf, or add a new in the script.<br>
* mqttpublishWATT : send the status of charger / discharger <br>(positive = discharger, negative = charger)<br>
* mqttpublishSOC  = SOC status of BMS 0..100 (if used)

Usage / Installation:<br>
All settings can be configured in BSsetup.conf<br>
All the options are explained or self explaining in detail in the conf file. <br>
For all devices exists a testprogram in the devices folder (e.g. lt232test for Lumentree) <br>
Here you can test all devcies seperatly and get the right "/dev/..." and id needed IDs for the access, before running the BatteryScript<br>

Change to executeable by chmod 755 BatteryScript.py<br>
Change to executeable by chmod 755 BSstart.py<br>
`Run: sudo chmod 755 BatteryScript.py`<br>
`Run: sudo chmod 755 BSstart.py`<br>
<br>
For first test just start the script after you configuerd the BSsetup.conf<br>
`./BatteryScript.py`<br>


To start using TMUX you can ./BSstart.py 0<br>
`./BSstart.py 0`<br><br>
Since I forget always the command to attach to the tmux window just call:<br>
`./ShowBS.sh`<br>
or<br>
`./BSstart.py 9`<br>
To detach, press CTRL+"B" -> release -> Press "D"<br>

`Options for BSstart [0..3,9]`<br>
Default "0" just starts the script,<br>
1..3 can be definded on your own startup procedure e.g. different settings for summer / winter<br>
9: show the tmux console"<br>
For a 10 second delay call BSstart.py with [10..13] (network boot delay)

**Tmux Startup**<br>
Run during startup:<br>
Thee are several ways to start the script automatically.<br>
I use an entry in cron to start the BSstart.py<br>

```
crontab -e
(add at the end:)
@reboot /home/pi/ABCDs/BSstart.py 10
```
Change the path to the right one.<br>
Use 10 as argument to be sure that network is up.

**systemd startup**<br>
To use the script as a service copy the file ABCDS.service to /etc/systemd/system (not tested now, tmux is recommended)<br>
`sudo cp ABCDS.service /etc/systemd/system`<br>
`sudo systemctl daemon-reload`<br>
`systemctl start book-scraper`<br><br>

**Additional Features**<br>
GPIO: <br>
Upto 4 GPIO buttons are already prepared, but you have to implement the action yourself<br>
<br>
LCD:<br>
I added a cheap 2x16 Character LCD with i2c interface.<br>
Use the green one, because it can run without backlight.<br>
The statusinfo is displayed on it.<br>
Installation: <br>
Enable i2c with <br>
`sudo raspi-config -> Interfaces`<br>
Install python3 smbus lib:<br>
`sudo apt install python3-smbus`<br>
<br>
Webserver:<br>
An integrated webserver at port 9000 is implemented to provide information and some interaction like restart, reboot, ... <br>
`http://[IP_of_Raspi]:9000`<br>

**Installation:<br>**
Automatic installation:<br>
`wget -O - https://github.com/MacGH23/BatteryScript_ABCDs/blob/ABCDs_install.sh | sudo bash`<br>

Manual Install with Git and clone the repository:<br>
`sudo apt install git`<br>
`git clone https://github.com/MacGH23/BatteryScript_ABCDs.git BatteryScript_ABCDs`<br>
Some python lib needed. Please install:<br>
`pip3 install pyserial`<br>
`pip3 install paho-mqtt`<br>
`--> if you already have installed paho-mqtt < 2.0 you have to update to 2.x` <br>
`pip3 install -U paho-mqtt` <br>
`apt install pip3 python3-can` <br>
`pip3 install ifcfg`<br>
`pip3 install minimalmodbus`<br>
`pip3 install configupdater`<br>
`pip3 install psutil`<br>
`pip3 install schedule`<br>
`pip3 install rpi`<br>
Install Tmux<br>
`sudo apt install tmux`<br>

For the serial communication with Lumentree and BMS the user must be added to dialout group<br>
`sudo usermod -a -G tty $USER`<br>

**Lumentree installation hints:<br>**
- Disable ModemManager to prevent scanning COM ports<br>
`sudo systemctl stop ModemManager`<br>
`sudo systemctl disable ModemManager`<br>

- Lumentree should not be updated too quickly <br>
Setting recommendation: <br>
LastDisChargePower_delta = 15 (between 10..20)<br>
DisChargerPowerCalcCount = 4 (or higher)<br> 
If you have problems (no answer or checksum error) with the USB RS232 adapter it could be that Lumentree DSUB9 connector is not 100% compatible with RS232 spec. <br>
It uses <br>
PIN2 : TX<br>
PIN3 : RX<br>
PIN5 : GND<br>
PIN9 : 12V <-- This can cause communication errors or defect for the USB<->RS232 adapter.<br>
In this case use a additional cable from the USB RS232 which only uses PIN2, PIN3, GND (USB -> RS232 -> Cable PIN2/3/GND -> Lumentree)<br>
Or remove PIN9 from the RS232 adapter<br>
Or use a RS232 port protector (1:1) and remove PIN9 <br>
![RS232_pp](/pictures/RS232_portprotect.jpg "RS232pp")<br>

**Meanwell installation hints (you take the risk !!):<br>**
- BIC-2200 (need to be installed by a electrically qualified person):<br>
Normally a ON Jumperwire is installed in the device.<br>
Before setup everything (including AC/DC cables) remove this cable (prevent to start before configured).<br>
Connect the CANBus cable to the RasPi but **not** the DC wires.<br>
Now connect it to AC.<br>
The Device should start itself but should not do any AC<->DC conversion.<br>
Run the script the first time and allow to set the needed parameter.<br>
After that you need do a AC power cycle. <br>
Now connect the DC wires to the battery during it is OFF and<br>
connect the ON Jumperwire back to device.<br>
Connect it to AC and run the script (after configuration of cource).<br>
- NPB:<br>
Connect the CANBus cable to the RasPi but **not** the the DC wires to the battery.<br>
Connect it to AC and switch it on.<br>
Run the script the first time and allow to set the needed parameter.<br>
After that you need do a AC power cycle.<br>
Now connect the DC wires to the battery during it is OFF.<br>
Run the script (after configuration of cource).<br>
<br>

**DALY BMS hints:<br>**
DALY BMS needs quite long to answer, use min. 2 seconds for meter update<br>


**CAN devices hints:<br>**
If you see problems during init of CAN device, check / add an entry in<br>
` sudo nano /etc/hosts`  <br>
127.0.1.1       [Hostname of your Raspberry] <br>

**Add new devices:<br>**
You have to provide the interface to the device. If possible add a class in a subfolder for easier handling:<br>
Add a:<br>
* Dis or Charger_[Device] function for the final communication<br>
* Add the devices in the StartStop[Dis]Charger functions
* For BMS devices see the BMS sections for it
* Add the initialisation and shutdown code in "main" and "onexit"<br><br>

**Credits:<br>**
Thanks to:<br>
https://github.com/stcan/meanwell-can-control for first idea for this script<br>
https://github.com/reserve85/HoymilesZeroExport where I take the code for the http meter request<br>
https://github.com/fah/jk-bms for the JKBMS interface<br>
https://github.com/dreadnought/python-daly-bms for Daly BMS interface

