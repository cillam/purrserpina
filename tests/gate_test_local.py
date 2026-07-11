#!/usr/bin/env python3
"""Bench test: the LOCAL person-gate — snap -> MobileNet-SSD "is someone there?"

The race winner from log 05: a few hundred ms, no network, no API cost.
Prints the best person-confidence score each pass — that score is the tuning
dial for CONFIDENCE (currently 0.50). Lower it if real people at porch
distance score low while empty frames stay near zero.

Integration seam: person_present() -> bool is exactly what the brain will
import/copy — swap the detector later without touching anything else.

Model files (one-time download, ~4 MB, offline forever after):
  assets/models/detect.tflite
  assets/models/labelmap.txt
(from the coco_ssd_mobilenet_v1_1.0_quant zip — see README asset manifest)

Deps: ai-edge-litert (pip, --break-system-packages), python3-pil (apt).

Run from anywhere:  python3 tests/gate_test_local.py
"""
import time
from pathlib import Path

import numpy as np
from PIL import Image
from picamera2 import Picamera2

# tflite-runtime is dead; LiteRT is the successor. Same model files, new package.
try:
    from ai_edge_litert.interpreter import Interpreter
except ImportError:                                  # older installs
    from tflite_runtime.interpreter import Interpreter

# --- repo anchoring (tests/ lives one level below the repo root) -------------
ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "assets" / "models"
MODEL_FILE = MODELS / "detect.tflite"
LABEL_FILE = MODELS / "labelmap.txt"

# --- tuning -------------------------------------------------------------------
CONFIDENCE = 0.50        # the dial: person score >= this counts as "someone there"
SNAP_SIZE = (1280, 720)  # capture size; model input is resized to 300x300 below
LOOP_PAUSE = 1.0         # seconds between passes while bench testing

# --- model setup ---------------------------------------------------------------
if not MODEL_FILE.exists():
    raise SystemExit(
        f"Model not found: {MODEL_FILE}\n"
        "Download coco_ssd_mobilenet_v1_1.0_quant and unzip detect.tflite + "
        "labelmap.txt into assets/models/ (see README asset manifest)."
    )

labels = [line.strip() for line in LABEL_FILE.read_text().splitlines()]
# Some labelmaps start with a '???' placeholder row; find "person" by name.
PERSON_ID = labels.index("person")

interpreter = Interpreter(model_path=str(MODEL_FILE), num_threads=4)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# --- camera ----------------------------------------------------------------------
picam2 = Picamera2()
picam2.configure(picam2.create_still_configuration(main={"size": SNAP_SIZE}))
picam2.start()
picam2.set_controls({"AfMode": 2})
time.sleep(2)                                     # settle + focus


def best_person_score() -> float:
    """Snap a frame, run the detector, return the best 'person' confidence."""
    frame = picam2.capture_array()                # RGB numpy array
    img = Image.fromarray(frame).convert("RGB").resize((300, 300))
    tensor = np.expand_dims(np.asarray(img, dtype=np.uint8), axis=0)

    interpreter.set_tensor(input_details[0]["index"], tensor)
    interpreter.invoke()

    classes = interpreter.get_tensor(output_details[1]["index"])[0]
    scores = interpreter.get_tensor(output_details[2]["index"])[0]

    person_scores = [s for c, s in zip(classes, scores) if int(c) == PERSON_ID]
    return max(person_scores, default=0.0)


def person_present() -> bool:
    """The seam the brain will use. Fail-open is the LAW: on any error, the
    PIR already voted yes, so a broken gate must never snub a real kid."""
    try:
        return best_person_score() >= CONFIDENCE
    except Exception as e:
        print(f"   gate error ({e}) -> fail-open, treating as person")
        return True


if __name__ == "__main__":
    print(f"Local gate up. Threshold {CONFIDENCE}. Ctrl+C to stop.\n")
    while True:
        t0 = time.time()
        score = best_person_score()
        verdict = "PERSON" if score >= CONFIDENCE else "empty"
        print(f"gate: {time.time() - t0:.2f}s  best person score = {score:.2f}  -> {verdict}")
        time.sleep(LOOP_PAUSE)
