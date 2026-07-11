#!/usr/bin/env python3
"""Voice lab: audition Piper's knobs live before committing. No GPIO.

Type a line -> she speaks it with the current settings.
Type a command to turn a knob:
    :volume 1.0      flat gain (no variation)
    :length 1.2      speed, INVERSE — bigger is slower
    :noise 0.667     tone wobble
    :noisew 0.8      timing wobble
    :show            print current settings
    :quit

Locked production settings (the brain's): volume 1.0, length_scale 1.2,
noise_scale 0.667, noise_w_scale 0.8 — the lab starts there.
Piper has NO pitch control; depth is a post-processing job (pedalboard, deferred).

Voice files live in assets/voices/ — BOTH the .onnx and its .onnx.json
sidecar. Piper silently needs both; the sidecar is the file selective
copies orphan.

Run from anywhere:  python3 tests/voice_test.py
"""
import subprocess
import wave
from pathlib import Path

from piper import PiperVoice, SynthesisConfig

# --- repo anchoring (tests/ lives one level below the repo root) -------------
ROOT = Path(__file__).resolve().parent.parent
VOICES = ROOT / "assets" / "voices"
VOICE_ONNX = VOICES / "en_US-kristin-medium.onnx"

WAV = Path("/tmp/voice_test.wav")

if not VOICE_ONNX.exists():
    raise SystemExit(
        f"Voice not found: {VOICE_ONNX}\n"
        "Download en_US-kristin-medium (.onnx AND .onnx.json) from HuggingFace "
        "rhasspy/piper-voices into assets/voices/ (see README asset manifest)."
    )
if not VOICE_ONNX.with_suffix(".onnx.json").exists():
    raise SystemExit(
        f"The .onnx is here but its sidecar is missing: {VOICE_ONNX}.json\n"
        "Piper silently needs both — copy the .onnx.json over too."
    )

voice = PiperVoice.load(str(VOICE_ONNX))

# start at the locked production settings
knobs = {
    "volume": 1.0,
    "length_scale": 1.2,
    "noise_scale": 0.667,
    "noise_w_scale": 0.8,
}

COMMANDS = {  # command name -> knob key
    "volume": "volume",
    "length": "length_scale",
    "noise": "noise_scale",
    "noisew": "noise_w_scale",
}


def show():
    print("   " + "  ".join(f"{k}={v}" for k, v in knobs.items()))


def speak(text: str):
    cfg = SynthesisConfig(**knobs)
    with wave.open(str(WAV), "wb") as f:
        voice.synthesize_wav(text, f, syn_config=cfg)
    subprocess.run(["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet", str(WAV)])


print("Voice lab — kristin. Type a line to hear it, :show for settings, :quit to leave.")
show()

while True:
    try:
        line = input("\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not line:
        continue
    if line.startswith(":"):
        parts = line[1:].split()
        cmd = parts[0].lower()
        if cmd in ("quit", "q", "exit"):
            break
        if cmd == "show":
            show()
        elif cmd in COMMANDS and len(parts) == 2:
            try:
                knobs[COMMANDS[cmd]] = float(parts[1])
                show()
            except ValueError:
                print("   need a number, e.g. :length 1.3")
        else:
            print("   commands: :volume :length :noise :noisew :show :quit")
        continue
    speak(line)

print("Done.")
