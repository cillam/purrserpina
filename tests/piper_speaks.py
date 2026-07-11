#!/usr/bin/env python3
"""
Purrserpina — ears + voice test.

Motion wakes her, she listens until you stop talking, transcribes your words
offline (faster-whisper), and echoes them back in her Piper voice with the jaw
moving in time. This is the full hear-and-speak loop, minus the Claude brain
(she repeats you instead of generating a fortune).

Run:  python3 ears_test_piper.py     (Ctrl+C to stop)
"""

import subprocess
import wave
import numpy as np
import sounddevice as sd
from time import sleep
from gpiozero import MotionSensor, RGBLED, Servo
from faster_whisper import WhisperModel
from piper import PiperVoice, SynthesisConfig

# ----------------------------------------------------------------------
# Hardware
# ----------------------------------------------------------------------
pir  = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
jaw  = Servo(18)
jaw.detach()                            # start limp + silent, no idle twitch

# ----------------------------------------------------------------------
# Listening config (stop-on-silence)
# ----------------------------------------------------------------------
MIC_RATE          = 48000               # the mic's real capture rate
BLOCK_SEC         = 0.1                  # check the level every 100 ms
SILENCE_THRESHOLD = 0.02                # below this = quiet; tune to your room
SILENCE_HANG      = 0.8                  # stop after this many seconds of quiet
MAX_SECONDS       = 8                    # hard cap so noise can't record forever
START_TIMEOUT     = 5                    # give up if nobody speaks within this

MOUTH_OPEN, MOUTH_SHUT, FLAP = 0.3, -0.3, 0.13

# ----------------------------------------------------------------------
# Voice (Piper) — locked settings
# ----------------------------------------------------------------------
VOICE = "/home/cillam/piper-voices/en_US-kristin-medium.onnx"

VOLUME        = 1.0
LENGTH_SCALE  = 1.2                      # gently slowed for an unhurried draw
NOISE_SCALE   = 0.667                    # kristin's default expressiveness
NOISE_W_SCALE = 0.8                      # kristin's default rhythm

syn = SynthesisConfig(
    volume=VOLUME,
    length_scale=LENGTH_SCALE,
    noise_scale=NOISE_SCALE,
    noise_w_scale=NOISE_W_SCALE,
    normalize_audio=True,
)

# ----------------------------------------------------------------------
# Load models once
# ----------------------------------------------------------------------
print("Loading Purrserpina's ears and voice...")
model = WhisperModel("base.en", device="cpu", compute_type="int8", cpu_threads=4)
voice = PiperVoice.load(VOICE)
print("Ready.\n")


def listen():
    """Record until the speaker pauses, then transcribe. Returns text ('' if silent)."""
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
                        break                       # they've stopped talking
            else:
                if loud:
                    speaking = True                 # they just started
                    frames.append(data.copy())
                elif i >= start_blocks:
                    break                           # nobody ever spoke

    if not frames:
        return ""

    audio = np.concatenate(frames).flatten()
    print(f"   (recorded {len(audio) / MIC_RATE:.1f}s)")
    trim = len(audio) - (len(audio) % 3)            # 48k -> 16k, clean 3:1
    audio16 = audio[:trim].reshape(-1, 3).mean(axis=1).astype(np.float32)
    segments, _ = model.transcribe(
        audio16, beam_size=3, language="en", vad_filter=True,
    )
    return " ".join(seg.text for seg in segments).strip()


def say(text):
    """Speak with Piper's voice while flapping the jaw to the audio."""
    with wave.open("/tmp/purr.wav", "wb") as wav:
        voice.synthesize_wav(text, wav, syn_config=syn)
    player = subprocess.Popen(["ffplay", "-autoexit", "-nodisp",
                               "-loglevel", "quiet", "/tmp/purr.wav"])
    while player.poll() is None:
        jaw.value = MOUTH_OPEN; sleep(FLAP)
        jaw.value = MOUTH_SHUT; sleep(FLAP)
    jaw.value = MOUTH_SHUT; sleep(0.3); jaw.detach()


# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------
print("Purrserpina sleeps. Walk up to wake her. (Ctrl+C to stop)\n")

while True:
    pir.wait_for_motion()
    eyes.color = (0.4, 0, 0.5)          # purple — she stirs
    print("Listening... speak now.")
    heard = listen()

    eyes.color = (1, 0, 0)              # red — she processes
    if heard:
        print(f"   Heard: {heard!r}")
        say(f"You said: {heard}")
    else:
        print("   (silence)")
        say("The spirits heard nothing.")

    sleep(0.5)
    eyes.off()
    print("...she sinks back into the dark.\n")
