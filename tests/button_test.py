from gpiozero import Button
from signal import pause

btn = Button(24)
btn.when_pressed = lambda: print("pressed!")
pause()

