#!/usr/bin/env python3
"""
Purrserpina — ears + voice test (with listening cues + timing).

Signals the guest whose turn it is:
  - She speaks a short invitation when she wakes ("...speak, and I shall listen").
  - Her eyes pulse GREEN while she's recording you (your turn).
  - They go steady RED while she thinks, BLUE-WHITE while she answers.

Still prints transcribe/synthesize times so we can see where the delay lives.

Run:  python3 ears_test_piper.py     (Ctrl+C to stop)
"""

import subprocess
import wave
import numpy as np
import sounddevice as sd
from time import sleep, perf_counter
from gpiozero import MotionSensor, RGBLED, Servo
from faster_whisper import WhisperModel
from piper import PiperVoice, SynthesisConfig

# ----------------------------------------------------------------------
# Hardware
# ----------------------------------------------------------------------
pir  = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
jaw  = Servo(18)
jaw.detach()

# eye-state colors (R, G, B), 0.0-1.0
WAKE_COLOR     = (0.4, 0.0, 0.5)        # purple     — stirring / greeting
LISTEN_COLOR   = (0.0, 1.0, 0.0)        # green      — your turn (pulses)
THINK_COLOR    = (1.0, 0.0, 0.0)        # red        — working
SPEAK_COLOR    = (0.6, 0.8, 1.0)        # blue-white — answering

GREETING = "Mmm. A visitor. Speak, and I shall listen."

# ----------------------------------------------------------------------
# Listening config (stop-on-silence)
# ----------------------------------------------------------------------
MIC_RATE          = 48000
BLOCK_SEC         = 0.1
SILENCE_THRESHOLD = 0.02
SILENCE_HANG      = 0.5
MAX_SECONDS       = 8
START_TIMEOUT     = 5

MOUTH_OPEN, MOUTH_SHUT, FLAP = 0.3, -0.3, 0.13

# ----------------------------------------------------------------------
# Voice (Piper)
# ----------------------------------------------------------------------
VOICE = "/home/cillam/piper-voices/en_US-kristin-medium.onnx"

syn = SynthesisConfig(
    volume=1.0,
    length_scale=1.2,
    noise_scale=0.667,
    noise_w_scale=0.8,
    normalize_audio=True,
)

# ----------------------------------------------------------------------
# Load models once
# ----------------------------------------------------------------------
print("Loading Purrserpina's ears and voice...")
model = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=4)
voice = PiperVoice.load(VOICE)
print("Ready.\n")


def record():
    """Record until the speaker pauses. Returns 16 kHz mono audio, or None if silent."""
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
        return None

    audio = np.concatenate(frames).flatten()
    print(f"   (recorded {len(audio) / MIC_RATE:.1f}s)")
    trim = len(audio) - (len(audio) % 3)            # 48k -> 16k, clean 3:1
    return audio[:trim].reshape(-1, 3).mean(axis=1).astype(np.float32)


def transcribe(audio16):
    """Turn recorded audio into text. Returns '' for silence."""
    if audio16 is None:
        return ""
    t0 = perf_counter()
    segments, _ = model.transcribe(
        audio16, beam_size=1, language="en", vad_filter=True,
    )
    text = " ".join(seg.text for seg in segments).strip()
    print(f"   transcribe: {perf_counter() - t0:.1f}s")
    return text


def say(text):
    """Speak with Piper's voice while flapping the jaw to the audio."""
    t0 = perf_counter()
    with wave.open("/tmp/purr.wav", "wb") as wav:
        voice.synthesize_wav(text, wav, syn_config=syn)
    print(f"   synthesize: {perf_counter() - t0:.1f}s")

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

    eyes.color = WAKE_COLOR                      # purple — she stirs
    print("She wakes and greets the guest.")
    say(GREETING)                                # verbal cue: "speak, and I shall listen"

    # green pulse = "your turn, I'm listening" (runs on a background thread)
    eyes.pulse(on_color=LISTEN_COLOR, off_color=(0, 0, 0),
               fade_in_time=0.6, fade_out_time=0.6)
    print("Listening... (eyes pulsing green)")
    audio16 = record()

    eyes.color = THINK_COLOR                      # red — working (stops the pulse)
    heard = transcribe(audio16)

    eyes.color = SPEAK_COLOR                       # blue-white — answering
    if heard:
        print(f"   Heard: {heard!r}")
        say(f"You said: {heard}")
    else:
        print("   (silence)")
        say("The spirits heard nothing.")

    sleep(0.5)
    eyes.off()                                     # back to sleep
    print("...she sinks back into the dark.\n")
