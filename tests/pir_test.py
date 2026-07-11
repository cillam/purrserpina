from gpiozero import MotionSensor
from time import sleep

pir = MotionSensor(23)
print("Warming up, hold still ~30-60 seconds...")
pir.wait_for_no_motion()
print("Ready. Wave your hand.")

while True:
    pir.wait_for_motion()
    print("Motion detected!")
    pir.wait_for_no_motion()
    print("...clear")
