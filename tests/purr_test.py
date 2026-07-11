from gpiozero import MotionSensor, RGBLED, Servo
from time import sleep
from signal import pause

pir  = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
jaw  = Servo(18)

jaw.detach()          # start silent and still

def wake():
    print("Motion — Purrserpina stirs...")
    eyes.color = (1, 0, 0)
    for _ in range(3):
        jaw.min(); sleep(0.3)
        jaw.max(); sleep(0.3)
    jaw.detach()      # go limp and silent again — kills the idle twitch

def rest():
    print("...still again.")
    eyes.off()

pir.when_motion    = wake
pir.when_no_motion = rest

print("Purrserpina is watching. Wave to wake her. Ctrl+C to stop.")
pause()
