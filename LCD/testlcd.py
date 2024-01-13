import HD44780_i2c
from time import *

lcd = i2clcd.lcd()

lcd.lcd_clear()
lcd.lcd_display_string("Test1", 1)
lcd.lcd_display_string("Test2", 2)
lcd.lcd_display_string("Test3", 3)
lcd.lcd_display_string("Test4", 4)
