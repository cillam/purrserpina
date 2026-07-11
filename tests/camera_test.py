from picamera2 import Picamera2
from time import sleep

cam = Picamera2()
config = cam.create_still_configuration()   # full-res stills for the IMX708
cam.configure(config)
cam.start()

# Module 3 has autofocus — give it a moment, then trigger a focus cycle
cam.set_controls({"AfMode": 2})             # 2 = continuous autofocus
sleep(2)

cam.capture_file("/home/cillam/camera_test.jpg")
cam.stop()
print("Saved camera_test.jpg")
