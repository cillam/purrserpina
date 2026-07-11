#!/usr/bin/env python3
"""Fallback echo test: the full hear -> speak loop MINUS the brain.

Kept as the brain's fallback (log 04): if purrserpina_brain.py misbehaves,
this proves everything below the Claude call still works. Walk up and:

  wake (purple) -> spoken greeting -> PULSING GREEN = your turn ->
  record until you stop talking -> RED = thinking -> transcribe offline ->
  BLUE-WHITE = answering -> she echoes your words back in kristin's voice,
  jaw moving in time -> sleep.

Prints transcribe:/synthesize: timings — the original latency instruments.

Assets: kristin's .onnx + .onnx.json sidecar in assets/voices/.
(The Whisper tiny.en model auto-downloads to its own cache on first run —
needs WiFi that once — it is not a repo asset.)

Run from anywhere:  python3 tests/ears_test_piper.py
"""
import subprocess
import wave
from pathlib import Path
from time import sleep, time

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from gpiozero import MotionSensor, RGBLED, Servo
from piper import PiperVoice, SynthesisConfig

# --- repo anchoring (tests/ lives one level below the repo root) -------------
ROOT = Path(__file__).resolve().parent.parent
VOICES = ROOT / "assets" / "voices"
VOICE_ONNX = VOICES / "en_US-kristin-medium.onnx"
WAV = Path("/tmp/purr_echo.wav")

if not VOICE_ONNX.exists() or not VOICE_ONNX.with_suffix(".onnx.json").exists():
    raise SystemExit(
        f"Voice files missing under {VOICES}\n"
        "Need BOTH en_US-kristin-medium.onnx and .onnx.json (HuggingFace "
        "rhasspy/piper-voices — see README asset manifest)."
    )

# --- ears (mic can only do 48 kHz; Whisper wants 16 kHz -> downsample 3:1) ----
MIC_RATE = 48000
BLOCK = MIC_RATE // 10        # 100 ms blocks
THRESHOLD = 0.02              # speech level — tune to the room
SILENCE_HANG = 1.3            # quiet seconds that end the turn (0.5 cut off breaths)
START_WAIT = 7.0              # seconds to wait for the guest to begin
MAX_SECONDS = 10.0            # max talking length

# --- jaw ------------------------------------------------------------------------
MOUTH_SHUT = -0.3
MOUTH_OPEN = 0.3
FLAP = 0.13

# --- eye states ------------------------------------------------------------------
WAKE = (0.4, 0, 0.5)          # purple
LISTEN = (0, 1, 0)            # green — PULSES
THINK = (1, 0, 0)             # red
SPEAK = (0.6, 0.8, 1.0)       # blue-white

pir = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
jaw = Servo(18)
jaw.detach()

print("Loading Whisper (tiny.en)...")
whisper = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=4)
print("Loading Piper (kristin)...")
voice = PiperVoice.load(str(VOICE_ONNX))
SYN = SynthesisConfig(volume=1.0, length_scale=1.2,
                      noise_scale=0.667, noise_w_scale=0.8)


def set_eyes(color):
    """gpiozero gotcha: setting .color does NOT stop a running pulse thread —
    it kept overwriting THINK red. Explicit off() first kills the pulse."""
    eyes.off()
    eyes.color = color


def rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(block ** 2)))


def record():
    """Stop-on-silence recording, two independently bounded phases:
    wait-to-begin (START_WAIT) vs max-talking-length (MAX_SECONDS).
    Returns 16 kHz float32 audio, or None if the guest never spoke."""
    blocks = []
    with sd.InputStream(samplerate=MIC_RATE, channels=1,
                        dtype="float32", blocksize=BLOCK) as stream:
        # phase 1: wait for speech to begin
        waited = 0.0
        peak = 0.0
        while True:
            block, _ = stream.read(BLOCK)
            level = rms(block)
            peak = max(peak, level)
            if level >= THRESHOLD:
                blocks.append(block.copy())
                break
            waited += 0.1
            if waited >= START_WAIT:
                print(f"   (no speech — peak input {peak:.4f}; "
                      "near zero = mic dead, low = too quiet)")
                return None
        # phase 2: record until silence hangs
        talking = 0.1
        silence = 0.0
        while True:
            block, _ = stream.read(BLOCK)
            blocks.append(block.copy())
            talking += 0.1
            if rms(block) < THRESHOLD:
                silence += 0.1
                if silence >= SILENCE_HANG:
                    break
            else:
                silence = 0.0
            if talking >= MAX_SECONDS:
                break
    audio = np.concatenate(blocks)[:, 0]
    # 48k -> 16k: average every 3 samples (doubles as a cheap anti-alias filter)
    n = len(audio) - (len(audio) % 3)
    return audio[:n].reshape(-1, 3).mean(axis=1).astype(np.float32)


def transcribe(audio) -> str:
    t0 = time()
    segments, _ = whisper.transcribe(audio, beam_size=1, language="en",
                                     vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    print(f"   transcribe: {time() - t0:.2f}s")
    return text


def say(text: str):
    """Synthesize then play with the jaw flapping until the audio ends."""
    t0 = time()
    with wave.open(str(WAV), "wb") as f:
        voice.synthesize_wav(text, f, syn_config=SYN)
    print(f"   synthesize: {time() - t0:.2f}s")
    player = subprocess.Popen(["ffplay", "-autoexit", "-nodisp",
                               "-loglevel", "quiet", str(WAV)])
    while player.poll() is None:
        jaw.value = MOUTH_OPEN
        sleep(FLAP)
        jaw.value = MOUTH_SHUT
        sleep(FLAP)
    jaw.value = MOUTH_SHUT
    sleep(0.3)
    jaw.detach()


print("\nPurrserpina (echo mode) sleeps. Walk up to wake her. Ctrl+C to stop.\n")
try:
    while True:
        pir.wait_for_motion()

        set_eyes(WAKE)
        print("Someone's there...")
        say("Mmm. A visitor. Speak, and I shall listen.")

        eyes.pulse(fade_in_time=0.7, fade_out_time=0.7, on_color=LISTEN)
        print("Listening (green pulse)...")
        audio = record()

        set_eyes(THINK)
        if audio is None:
            say("Hmph. The silent type. How tedious.")
        else:
            heard = transcribe(audio)
            print(f'   heard: "{heard}"')
            set_eyes(SPEAK)
            if heard:
                say(f"You said... {heard}. Yes. The spirits heard it too.")
            else:
                say("Words were spoken, yet none reached me. Speak up, mortal.")

        eyes.off()
        print("...she sinks back into the dark.\n")
        sleep(2)  # no re-trigger gating on purpose — instant re-test on the bench
except KeyboardInterrupt:
    eyes.off()
    jaw.detach()
    print("\nStopped.")
