import subprocess
import numpy as np
import sounddevice as sd
from gpiozero import MotionSensor, RGBLED, Servo
from time import sleep

pir  = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
jaw  = Servo(18)
jaw.detach()                # start limp + silent, no idle twitch

THRESHOLD  = 0.05           # use whatever value you tuned to last time
SAMPLERATE = 44100
CHUNK      = 0.3

MOUTH_SHUT = -0.3           # jaw positions while talking — tune once she's
MOUTH_OPEN =  0.3           # mounted, to whatever actually opens/closes her
FLAP       = 0.13           # seconds per open or shut — smaller = chattier

def mic_level():
    audio = sd.rec(int(CHUNK * SAMPLERATE), samplerate=SAMPLERATE,
                   channels=1, dtype="float32")
    sd.wait()
    return float(np.sqrt(np.mean(audio ** 2)))

def say(text):
    """Speak a line while flapping the jaw in time with the audio."""
    subprocess.run(["espeak-ng", "-v", "en-us+f3", "-s", "140", "-p", "35",
                    "-w", "/tmp/purr.wav", text])
    player = subprocess.Popen(["ffplay", "-autoexit", "-nodisp",
                               "-loglevel", "quiet", "/tmp/purr.wav"])
    while player.poll() is None:        # keep flapping until the audio ends
        jaw.value = MOUTH_OPEN
        sleep(FLAP)
        jaw.value = MOUTH_SHUT
        sleep(FLAP)
    jaw.value = MOUTH_SHUT              # close her mouth...
    sleep(0.3)
    jaw.detach()                        # ...then go limp + silent

print("Purrserpina sleeps. Walk up to wake her. (Ctrl+C to stop)\n")

while True:
    pir.wait_for_motion()
    eyes.color = (0.4, 0, 0.5)          # dim purple — she stirs, stays lit
    print("Someone's there... her eyes open. Say hello.")

    while True:
        level = mic_level()
        print(f"   listening... level={level:.3f}")
        if level >= THRESHOLD:
            break

    print("She heard you.")
    eyes.color = (1, 0, 0)              # eyes flare red
    say("Ahh. A visitor. I have been expecting you. Sit, and I shall read your fate.")

    eyes.off()
    print("...she sinks back into the dark.\n")

