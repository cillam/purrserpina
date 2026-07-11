from gpiozero import RGBLED, MotionSensor
from signal import pause

eyes = RGBLED(red=17, green=27, blue=22)
pir = MotionSensor(23)

# her resting and alert colors — tweak these to taste
RESTING = (0, 0, 1)      # calm blue
ALERT   = (1, 0, 0)      # red when someone approaches

def someone_here():
    print("Motion — eyes alert")
    eyes.color = ALERT

def all_clear():
    print("Quiet — eyes resting")
    eyes.color = RESTING

eyes.color = RESTING
print("Warming up, hold still ~30-60 seconds...")
pir.wait_for_no_motion()
print("Ready.")

pir.when_motion = someone_here
pir.when_no_motion = all_clear

pause()
