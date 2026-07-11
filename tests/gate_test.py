#!/usr/bin/env python3
"""
gate_test.py -- Purrserpina camera gate, tested in isolation.

Snaps a photo, asks Claude (Haiku) "is there a person here?", prints the
verdict and how long each stage took. No GPIO, no brain changes.

Press Enter to snap again (camera stays warm between shots), Ctrl+C to quit.
Needs ANTHROPIC_API_KEY in the environment (~/.purrserpina.env via ~/.bashrc).
"""

import base64
import io
import time

from picamera2 import Picamera2
from PIL import Image
import anthropic

MODEL = "claude-haiku-4-5"
GATE_SIZE = (1280, 720)   # plenty for "is that a person"; small = fast upload
JPEG_QUALITY = 80

GATE_PROMPT = (
    "You are a motion-triggered doorbell camera check. "
    "Answer with exactly one word, YES or NO: "
    "is there at least one person visible in this image?"
)

client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from the environment

# --- camera setup (once; stays warm across snaps) ---
cam = Picamera2()
config = cam.create_still_configuration(main={"size": GATE_SIZE})
cam.configure(config)
cam.start()
cam.set_controls({"AfMode": 2})   # continuous autofocus on the IMX708
time.sleep(2)                     # let exposure + focus settle
print(f"Camera ready at {GATE_SIZE[0]}x{GATE_SIZE[1]}. Ctrl+C to quit.\n")


def snap_jpeg_b64():
    """Capture a frame, return (base64 jpeg string, capture seconds)."""
    t0 = time.time()
    arr = cam.capture_array()               # RGB numpy array
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return b64, time.time() - t0


def ask_gate(b64):
    """Send the photo to Haiku, return (verdict string, api seconds)."""
    t0 = time.time()
    resp = client.messages.create(
        model=MODEL,
        max_tokens=5,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64}},
                {"type": "text", "text": GATE_PROMPT},
            ],
        }],
    )
    verdict = resp.content[0].text.strip().upper()
    return verdict, time.time() - t0


shot = 0
while True:
    input("Enter to snap...")
    shot += 1

    b64, t_cap = snap_jpeg_b64()
    verdict, t_api = ask_gate(b64)

    total = t_cap + t_api
    person = verdict.startswith("YES")
    print(f"  shot {shot}: {'PERSON' if person else 'empty'}   "
          f"(raw: {verdict!r})")
    print(f"  capture: {t_cap:.2f}s   api: {t_api:.2f}s   "
          f"total gate: {total:.2f}s\n")
