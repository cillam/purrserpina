import subprocess
import numpy as np
import sounddevice as sd
from gpiozero import MotionSensor, RGBLED, Servo
from time import sleep
from faster_whisper import WhisperModel

# --- hardware ---
pir  = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
jaw  = Servo(18)
jaw.detach()

# --- config ---
MIC_RATE       = 48000      # what the mic can actually capture
WHISPER_RATE   = 16000      # what Whisper wants
RECORD_SECONDS = 4
MOUTH_OPEN, MOUTH_SHUT, FLAP = 0.3, -0.3, 0.13

print("Loading Purrserpina's ears (base model — downloads once, then local)...")
model = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=4)
print("Ready.\n")

def listen(seconds=RECORD_SECONDS):
    """Record at the mic's rate, downsample to 16 kHz, transcribe."""
    audio = sd.rec(int(seconds * MIC_RATE), samplerate=MIC_RATE,
                   channels=1, dtype="float32")
    sd.wait()
    audio = audio.flatten()
    trim = len(audio) - (len(audio) % 3)            # 48k -> 16k, clean 3:1
    audio16 = audio[:trim].reshape(-1, 3).mean(axis=1).astype(np.float32)
    segments, _ = model.transcribe(
        audio16,
        beam_size=3,        # most of the accuracy, less cost than 5
        language="en",
        vad_filter=True,    # strip silence/noise -> no hallucinated phrases
    )
    return " ".join(seg.text for seg in segments).strip()

def say(text):
    subprocess.run(["espeak-ng", "-v", "en-us+f3", "-s", "140", "-p", "35",
                    "-w", "/tmp/purr.wav", text])
    player = subprocess.Popen(["ffplay", "-autoexit", "-nodisp",
                               "-loglevel", "quiet", "/tmp/purr.wav"])
    while player.poll() is None:
        jaw.value = MOUTH_OPEN; sleep(FLAP)
        jaw.value = MOUTH_SHUT; sleep(FLAP)
    jaw.value = MOUTH_SHUT; sleep(0.3); jaw.detach()

print("Purrserpina sleeps. Walk up to wake her. (Ctrl+C to stop)\n")

while True:
    pir.wait_for_motion()
    eyes.color = (0.4, 0, 0.5)             # purple — she stirs
    print("Listening... speak now.")
    heard = listen()

    eyes.color = (1, 0, 0)                 # red — she processes
    if heard:
        print(f"   Heard: {heard!r}")
        say(f"You said: {heard}")
    else:
        print("   (silence)")
        say("The spirits heard nothing.")

    sleep(0.5)
    eyes.off()
    print("...she sinks back into the dark.\n")
