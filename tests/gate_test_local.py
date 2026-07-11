#!/usr/bin/env python3
"""
gate_test_local.py -- Purrserpina camera gate, fully local version.

Same job as gate_test.py (snap -> "is there a person?" -> verdict + timing),
but the detector runs on the Pi itself: no network, no API cost.

One-time setup on the Pi:

    pip install --break-system-packages ai-edge-litert
    mkdir -p ~/purr-models && cd ~/purr-models
    wget https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
    unzip coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip
    # gives detect.tflite + labelmap.txt

Press Enter to snap again (camera stays warm), Ctrl+C to quit.
"""

import os
import time

import numpy as np
from picamera2 import Picamera2
from PIL import Image

try:                                     # LiteRT: current package, new Pythons
    from ai_edge_litert.interpreter import Interpreter
except ImportError:                      # legacy name, Python <= 3.11 only
    from tflite_runtime.interpreter import Interpreter

MODEL_DIR = os.path.expanduser("~/purr-models")
MODEL_PATH = os.path.join(MODEL_DIR, "detect.tflite")
LABEL_PATH = os.path.join(MODEL_DIR, "labelmap.txt")

GATE_SIZE = (1280, 720)   # capture size -- match gate_test.py for a fair race
CONFIDENCE = 0.50          # min score to count a detection as a person

# --- labels ---
with open(LABEL_PATH) as f:
    labels = [line.strip() for line in f]
if labels and labels[0] == "???":   # some copies have a placeholder first row
    labels = labels[1:]
PERSON_IDS = {i for i, name in enumerate(labels) if name == "person"}

# --- detector setup (once) ---
interpreter = Interpreter(model_path=MODEL_PATH, num_threads=4)
interpreter.allocate_tensors()
inp = interpreter.get_input_details()[0]
outs = interpreter.get_output_details()
_, in_h, in_w, _ = inp["shape"]      # 300x300 for this model

# --- camera setup (once; stays warm across snaps) ---
cam = Picamera2()
config = cam.create_still_configuration(main={"size": GATE_SIZE})
cam.configure(config)
cam.start()
cam.set_controls({"AfMode": 2})      # continuous autofocus on the IMX708
time.sleep(2)
print(f"Camera ready at {GATE_SIZE[0]}x{GATE_SIZE[1]}, "
      f"model expects {in_w}x{in_h}. Ctrl+C to quit.\n")


def detect_person():
    """Snap + run the detector. Returns (person?, best score, capture s, infer s)."""
    t0 = time.time()
    arr = cam.capture_array()                          # RGB numpy array
    t_cap = time.time() - t0

    t0 = time.time()
    small = Image.fromarray(arr).resize((in_w, in_h))
    tensor = np.expand_dims(np.asarray(small, dtype=np.uint8), axis=0)
    interpreter.set_tensor(inp["index"], tensor)
    interpreter.invoke()

    classes = interpreter.get_tensor(outs[1]["index"])[0]   # class ids
    scores = interpreter.get_tensor(outs[2]["index"])[0]    # confidences

    best = 0.0
    for cls, score in zip(classes, scores):
        if int(cls) in PERSON_IDS and score > best:
            best = float(score)
    t_inf = time.time() - t0

    return best >= CONFIDENCE, best, t_cap, t_inf


shot = 0
while True:
    input("Enter to snap...")
    shot += 1

    person, score, t_cap, t_inf = detect_person()

    total = t_cap + t_inf
    print(f"  shot {shot}: {'PERSON' if person else 'empty'}   "
          f"(best person score: {score:.2f})")
    print(f"  capture: {t_cap:.2f}s   infer: {t_inf:.2f}s   "
          f"total gate: {total:.2f}s\n")
