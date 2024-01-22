# ABCDS: *A*utomatic (DIY) *B*attery *C*harge / *D*ischarge *S*cript

Python3 script for fully automatic charge and discharge a DIY battery for photovoltaic systems to provide a "zero feed-in".<br><br>
**WARNING - USE THIS SCRIPT TOTALLY ON YOUR OWN RISK !!! (needed to add ;-)<br><br>** 
The idea is that everyone can add new devices and provide it to the community.<br><br>
Current tested/running on a Raspberry Pi:
- Raspberry Pi Zero
- Raspberry Pi 2<br>

Should work on any Raspberry Pi. <br>

**Status Webserver:<br>**
For a better overview a own webserver at port 9000 is available.<br>
Here you can have a quick overview of the current status ans you can enable and disbale Charger and DisCharger

**Current supported hardware:<br>**
**Charger:**
* Meanwell BIC-2200<br>
* Meanwell NPB-[450/750/1200/1700]-[12/24/48/96]<br>
* Simulator, can be used for testing<br>

*Important Note for Meanwell devices !<br>*
Changing the output values are limited to 4.000.000 by design.<br>
Therefore several options are available to configure.<br>
- ZeroDeltaChargerWatt       =    30 (range in WATT without set device to new value)
- chargercounter = 8 (wait for change, multiply with METER updates in seconds.)<br>
e.g. (Meter update all 2 seconds) x (8) = only after 16 seconds an update will be send if necessary

**Discharger:**
* Meanwell BIC-2200<br>
* Lumentree (by ask4it) 600/1000/2000, upto 3 can be used in parallel<br>
* Simulator, can be used for testing

**BMS:**
* JKBMS with original JK RS485 interface adapter

**Power meter information:<br>**
To adjust everything automatically, you need to get the current power.<br>
Positive = Take power from the GRID<br>
Negative = Get power from PV<br>
* MQTT (get vlaues from any mqtt broker)
* Shelly (EM, 3EM, 3EMPro) (not tested)
* Tasmota (not tested)
* IOBroker via simple API
* EMLOG (not tested)
* VZlogger (not tested)
* Simulator, can be used for testing (random power value)<br>


Additional hardware needed, depending on the used hardware

Device / HW | Interface | Recommended
---|---|---|
Meanwell | CAN | [Waveshare RS485 CAN HAT](https://www.waveshare.com/rs485-can-hat.htm) or [Fischl USBTin](https://www.fischl.de/usbtin/)<br> ![Waveshare RS485CAN](/pictures/wavesharers485can.jpg "Waveshare RS485CAN")   ![Fischl USBTin](/pictures/usbtin.jpg "Fischl USBTin")
Lumentree | RS232 | Any simple USB to RS232 adapter<br> ![USB RS232](/pictures/usbrs232.jpg "USB RS232")
JKBMS | RS485 | [Waveshare RS485 CAN HAT](https://www.waveshare.com/rs485-can-hat.htm) with original JKRS485 adapter<br> ![JKBms RS485](/pictures/jkbms_rs485.JPG "JKBms RS485")


Meanwell devices using a small 2x7 pin connector from MPE for the CAN interface.<br> Normally a connector with 2 wires are part of the delievery. The connector is a [MPE BLC 14](https://www.reichelt.de/crimp-buchsenleiste-14-pol-mpe-blc-14-p247189.html?CCOUNTRY=445&LANGUAGE=de&nbc=1&&r=1) (partnumber 906-2-014-X-BS0A10) and [crimp pins](https://www.reichelt.de/crimpkontakt-fuer-mpe-blc-einzeln-mpe-cc222-p150922.html?CCOUNTRY=445&LANGUAGE=de&nbc=1&&r=1) (partnumber CC2-22/30-TT-RL)

Only the CAN wires are needed to install. See manual of the device where the CAN PINs are.

Lumentree devices uses a normal RS232 interface with modbus protocol.<br>
Easiest methode to connect is a simple USB to RS232 adapter.

JKBMS is optional. You have to use the original JK RS485 adapter and connect it to a RS485 interface at the Raspberry. <br>
Use the Waveshare CAN/RS485 HAT. Especially if you also use a CAN device.

MQTT publish:<br>
You can publish some data form the script to the mqtt server.<br>
Change the already implemented ones in the charger.conf, or add a new in the script.<br>
* mqttpublishWATT : send the status of charger / discharger <br>(positive = discharger, negative = charger)<br>
* mqttpublishSOC  = SOC status of BMS 0..100 (if used)

Usage:<br>
All settings can be configured in BSsetup.conf<br>
All the options are explained or self explaining in detail in the conf file. <br>

Change to executeable by chmod 755 BatteryScript.py<br>
Run: /.BatteryScript.py
To run the background tmux can be used.<br>
Start bach script is "start_tmux.sh" (also chmod it)<br>

Run during startup:<br>
Thee are several ways to start the script automatically.<br>
I use an entry in cron to start the tmux script<br>

```
crontab -e
(add at the end:)
@reboot bash /home/pi/BatteryScript/start_tmux.sh &
```
Change the path to the right one.

Since I forget always the command to attach to the tmux window just run (chmod before):<br>
`./ShowBS.sh` 
To detach, press CTRL+"B" -> release -> Press "D"

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
`sudo apt install python3-smbus`

**Installation:<br>**
Some python lib needed. Please install:<br>
`pip3 install pyserial`<br>
`pip3 install paho-mqtt`<br>
`pip3 install ifcfg`<br>
`pip3 install minimalmodbus`<br>
`pip3 install configupdater`<br><br>
For the serial communication with Lumentree and BMS the user must be added to dialout group<br>
`sudo usermod -a -G tty $USER`<br>

Change the file executeable with<br>
`sudo chmod 755 BatteryScript.py`<br>

For first test just start the script after you configuerd the chager.conf<br>
`./BatteryScript.py`<br>

To use the script as a service copy the file ABCDS.service to /etc/systemd/system<br>
`sudo cp ABCDS.service /etc/systemd/system`<br>
`sudo systemctl daemon-reload`<br>
`systemctl start book-scraper`<br>

To start using TMUX you can start_tmux.sh<br>
`./start_tmux.sh`<br>
To connect to Tmux:<br>
`./ShowBS.sh`<br>

**Credits:<br>**
Thanks to:<br>
https://github.com/stcan/meanwell-can-control for first idea for this script<br>
https://github.com/reserve85/HoymilesZeroExport where I take the code for the http meter request<br>
https://github.com/fah/jk-bms for the jkbms script

