#!/usr/bin/env python3
"""One-shot gate diagnostic. Stop purrserpina_brain.py first (the camera can't
be opened twice), stand in view, run:  python3 tests/gate_diag.py

Answers two questions:
  1. Is the camera giving a real picture?   (brightness + /tmp/gate_frame.jpg)
  2. What is the detector actually seeing?  (raw class ids, both label readings)
"""
import time
from pathlib import Path

import numpy as np
from PIL import Image
from picamera2 import Picamera2

try:
    from ai_edge_litert.interpreter import Interpreter
except ImportError:
    from tflite_runtime.interpreter import Interpreter

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "assets" / "models"
labels = [l.strip() for l in (MODELS / "labelmap.txt").read_text().splitlines()]
print(f"labelmap: {len(labels)} rows, first three = {labels[:3]}")
print(f"labels.index('person') = {labels.index('person')}   <- what the gate currently uses\n")

interp = Interpreter(model_path=str(MODELS / "detect.tflite"), num_threads=4)
interp.allocate_tensors()
inp, out = interp.get_input_details(), interp.get_output_details()

cam = Picamera2()
cam.configure(cam.create_still_configuration(main={"size": (1280, 720), "format": "BGR888"}))
cam.start()
cam.set_controls({"AfMode": 2})
time.sleep(2)

for n in range(3):
    frame = cam.capture_array()
    print(f"--- snap {n + 1}: shape {frame.shape}, mean brightness {frame.mean():.1f} "
          f"(near 0 = black frame)")
    Image.fromarray(frame).convert("RGB").save("/tmp/gate_frame.jpg")
    img = Image.fromarray(frame).convert("RGB").resize((300, 300))
    interp.set_tensor(inp[0]["index"], np.expand_dims(np.asarray(img, dtype=np.uint8), 0))
    interp.invoke()
    classes = interp.get_tensor(out[1]["index"])[0]
    scores = interp.get_tensor(out[2]["index"])[0]
    for c, s in sorted(zip(classes, scores), key=lambda t: -t[1])[:5]:
        c = int(c)
        as_is = labels[c] if c < len(labels) else "?"
        shifted = labels[c + 1] if c + 1 < len(labels) else "?"
        print(f"   class {c:3d}  score {s:.2f}   as-is: {as_is:12s}  offset+1: {shifted}")
    time.sleep(1)

cam.stop()
cam.close()
print("\nSaved the last frame to /tmp/gate_frame.jpg")
