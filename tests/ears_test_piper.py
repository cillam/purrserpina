import subprocess
import wave
import numpy as np
import sounddevice as sd
from gpiozero import MotionSensor, RGBLED, Servo
from time import sleep
from faster_whisper import WhisperModel
from piper import PiperVoice

# --- hardware ---
pir  = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
jaw  = Servo(18)
jaw.detach()

# --- audio config ---
MIC_RATE          = 48000
BLOCK_SEC         = 0.1
SILENCE_THRESHOLD = 0.02
SILENCE_HANG      = 0.8
MAX_SECONDS       = 8
START_TIMEOUT     = 5
MOUTH_OPEN, MOUTH_SHUT, FLAP = 0.3, -0.3, 0.13

VOICE = "/home/cillam/piper-voices/en_US-kristin-medium.onnx"

print("Loading Purrserpina's ears and voice...")
model = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=4)
voice = PiperVoice.load(VOICE)
print("Ready.\n")

def listen():
    """Record until the speaker pauses, then transcribe. Returns text."""
    block        = int(BLOCK_SEC * MIC_RATE)
    hang_blocks  = int(SILENCE_HANG / BLOCK_SEC)
    max_blocks   = int(MAX_SECONDS / BLOCK_SEC)
    start_blocks = int(START_TIMEOUT / BLOCK_SEC)

    frames, speaking, silent_run = [], False, 0

    with sd.InputStream(samplerate=MIC_RATE, channels=1, dtype="float32") as stream:
        for i in range(max_blocks):
            data, _ = stream.read(block)
            loud = float(np.sqrt(np.mean(data ** 2))) >= SILENCE_THRESHOLD

            if speaking:
                frames.append(data.copy())
                if loud:
                    silent_run = 0
                else:
                    silent_run += 1
                    if silent_run >= hang_blocks:
                        break
            else:
                if loud:
                    speaking = True
                    frames.append(data.copy())
                elif i >= start_blocks:
                    break

    if not frames:
        return ""

    audio = np.concatenate(frames).flatten()
    print(f"   (recorded {len(audio) / MIC_RATE:.1f}s)")
    trim = len(audio) - (len(audio) % 3)
    audio16 = audio[:trim].reshape(-1, 3).mean(axis=1).astype(np.float32)
    segments, _ = model.transcribe(
        audio16, beam_size=3, language="en", vad_filter=True,
    )
    return " ".join(seg.text for seg in segments).strip()

def say(text):
    """Speak with Piper's voice while flapping the jaw to the audio."""
    with wave.open("/tmp/purr.wav", "wb") as wav:
        voice.synthesize_wav(text, wav)
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
