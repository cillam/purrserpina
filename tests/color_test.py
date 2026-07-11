from gpiozero import RGBLED
from time import sleep

eyes = RGBLED(red=17, green=27, blue=22)

def set_color(red, green, blue):
    # gpiozero wants 0–1.0 per channel; we keep the familiar 0–255 scale
    # and convert here, so you can paste values straight from any color picker
    eyes.color = (red / 255, green / 255, blue / 255)

while True:
    set_color(255, 0, 0)      # red
    sleep(1)
    set_color(0, 255, 0)      # green
    sleep(1)
    set_color(0, 0, 255)      # blue
    sleep(1)
    set_color(255, 255, 0)    # yellow
    sleep(1)
    set_color(80, 0, 80)      # purple
    sleep(1)
    set_color(0, 255, 255)    # aqua
    sleep(1)
