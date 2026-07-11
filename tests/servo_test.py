from gpiozero import Servo
from time import sleep

jaw = Servo(18)
while True:
    jaw.min(); sleep(1)
    jaw.mid(); sleep(1)
    jaw.max(); sleep(1)
