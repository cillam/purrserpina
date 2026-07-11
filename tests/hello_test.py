import subprocess
import numpy as np
import sounddevice as sd
from gpiozero import MotionSensor, RGBLED
from time import sleep

pir  = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)

THRESHOLD  = 0.05      # volume that counts as "heard you" — tune this first run
SAMPLERATE = 44100     # your mic recorded fine at this rate
CHUNK      = 0.3       # seconds of sound measured per check

def mic_level():
    """Record a short chunk and return its loudness, 0.0–1.0."""
    audio = sd.rec(int(CHUNK * SAMPLERATE), samplerate=SAMPLERATE,
                   channels=1, dtype="float32")   # mono, like your mic
    sd.wait()
    return float(np.sqrt(np.mean(audio ** 2)))    # RMS = how loud it was

def say(text):
    """Synthesize a line, then play it through the speaker via ffplay."""
    subprocess.run(["espeak-ng", "-v", "en-us+f3", "-s", "140", "-p", "35",
                    "-w", "/tmp/purr.wav", text])
    subprocess.run(["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet",
                    "/tmp/purr.wav"])

print("Purrserpina sleeps. Walk up to wake her. (Ctrl+C to stop)\n")

while True:
    pir.wait_for_motion()
    eyes.color = (0.4, 0, 0.5)          # dim purple — she stirs, and stays lit
    print("Someone's there... her eyes open. Say hello.")

    while True:                          # listen until a sound is loud enough
        level = mic_level()
        print(f"   listening... level={level:.3f}")
        if level >= THRESHOLD:
            break

    print("She heard you.")
    eyes.color = (1, 0, 0)              # eyes flare from purple to red
    say("Ahh. A visitor. I have been expecting you. Sit, and I shall read your fate.")

    sleep(1)
    eyes.off()                          # settle back to sleep for the next guest
    print("...she sinks back into the dark.\n")

