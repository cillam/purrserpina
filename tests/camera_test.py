#!/usr/bin/env python3
"""Bench test: Camera Module 3 (IMX708) from Python via picamera2.

Proves: still config, continuous autofocus, settle, capture.
No GPIO, no brain — camera in isolation.

Run from anywhere:  python3 tests/camera_test.py
"""
from pathlib import Path
from time import sleep, time

from picamera2 import Picamera2

# --- repo anchoring (tests/ lives one level below the repo root) -------------
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "captures"          # gitignored with the rest of assets/
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_FILE = OUT_DIR / "camera_test.jpg"

picam2 = Picamera2()

# Full-res still off the IMX708 (4608x2592); Wide lens fisheyes at the edges by design.
config = picam2.create_still_configuration()
picam2.configure(config)

picam2.start()
picam2.set_controls({"AfMode": 2})              # 2 = continuous autofocus
print("Camera up. Settling / focusing for ~2s...")
sleep(2)

t0 = time()
picam2.capture_file(str(OUT_FILE))
print(f"capture: {time() - t0:.2f}s")
print(f"Saved -> {OUT_FILE}")
print("Pull it to the Mac to eyeball focus, e.g.:")
print(f"  scp cillam@purrserpina.local:{OUT_FILE} ~/Desktop/")

picam2.stop()
