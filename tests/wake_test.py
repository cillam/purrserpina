#!/usr/bin/env python3
"""
wake_test.py -- Purrserpina wake arbitration, tested in isolation.

Three wake sources, no camera, no audio:
  1. "gate"        -- PIR fires and the gate confirms a person
                      (gate is STUBBED here; returns GATE_STUB_ANSWER)
  2. "persistence" -- gate says no, but motion is sustained enough that
                      someone is probably there anyway (conservative!)
  3. "button"      -- GPIO 24 pressed; wakes unconditionally when asleep,
                      IGNORED while awake or cooling down

Eyes show state: purple = awake (fake audience), off = asleep.
The fake audience lasts AUDIENCE_FAKE_SECONDS -- mash the button during it
to prove the ignore guard. Ctrl+C to quit.

Wiring: button leg 1 -> GPIO 24 (physical pin 18), leg 2 -> any GND.
No resistor needed (internal pull-up).
"""

import threading
import time

from gpiozero import MotionSensor, RGBLED, Button

# ---------- tuning ----------
# Persistence: how demanding "someone is probably there" is.
# A person standing at the porch holds the PIR high; wind gives short blips.
PERSIST_WINDOW = 12.0        # seconds of history considered
PERSIST_MIN_ACTIVE = 5.0     # cumulative seconds PIR must be HIGH in window
PERSIST_MIN_EVENTS = 3       # distinct motion events required in window
PERSIST_BACKOFF = 240.0      # after a persistence wake, suppress that path
                             # this long (real script: only if no one spoke)

GATE_STUB_ANSWER = False     # pretend the camera gate says "no person",
                             # so the persistence path is what gets exercised
GATE_CHECK_COOLDOWN = 3.0    # min seconds between (stubbed) gate checks

AUDIENCE_FAKE_SECONDS = 10.0 # stand-in for hold_audience()
REARM_COOLDOWN = 5.0         # pause after audience before listening again

WAKE_COLOR = (0.4, 0, 0.5)   # purple

# ---------- hardware ----------
pir = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
button = Button(24)          # pulled up internally; press = to ground

# ---------- shared state ----------
wake_event = threading.Event()
wake_reason = None
awake = False                # covers audience AND cooldown
persist_suppressed_until = 0.0

# rolling motion history: list of [start_time, end_time_or_None]
motion_spans = []
motion_lock = threading.Lock()


def on_motion():
    with motion_lock:
        motion_spans.append([time.time(), None])


def on_no_motion():
    with motion_lock:
        if motion_spans and motion_spans[-1][1] is None:
            motion_spans[-1][1] = time.time()


def persistence_score():
    """Return (active_seconds, event_count) within the trailing window."""
    now = time.time()
    cutoff = now - PERSIST_WINDOW
    active = 0.0
    events = 0
    with motion_lock:
        # drop spans that ended before the window
        while motion_spans and motion_spans[0][1] is not None \
                and motion_spans[0][1] < cutoff:
            motion_spans.pop(0)
        for start, end in motion_spans:
            s = max(start, cutoff)
            e = end if end is not None else now
            if e > s:
                active += e - s
                events += 1
    return active, events


def gate_confirms_person():
    """STUB. Real version: snap a frame, run the local detector."""
    return GATE_STUB_ANSWER


def on_button():
    global wake_reason
    if awake:
        print("  [button] pressed -- IGNORED (already awake / cooling down)")
        return
    print("  [button] pressed -- summoned!")
    wake_reason = "button"
    wake_event.set()


pir.when_motion = on_motion
pir.when_no_motion = on_no_motion
button.when_pressed = on_button

print("PIR warming up, hold still ~30-60 seconds...")
pir.wait_for_no_motion()
print("Ready. Move for the PIR, or press the button.\n")

# ---------- main loop ----------
while True:
    # ----- asleep: watch wake sources -----
    wake_event.clear()
    wake_reason = None
    last_gate_check = 0.0

    while not wake_event.is_set():
        time.sleep(0.1)

        if not pir.motion_detected:
            continue

        now = time.time()

        # Path 1: motion + gate confirmation (rate-limited)
        if now - last_gate_check >= GATE_CHECK_COOLDOWN:
            last_gate_check = now
            if gate_confirms_person():
                wake_reason = "gate"
                wake_event.set()
                break

        # Path 2: conservative persistence (may be backed off)
        if now < persist_suppressed_until:
            continue
        active, events = persistence_score()
        if active >= PERSIST_MIN_ACTIVE and events >= PERSIST_MIN_EVENTS:
            print(f"  [persistence] {active:.1f}s active over "
                  f"{events} events -- probably someone")
            wake_reason = "persistence"
            persist_suppressed_until = now + PERSIST_BACKOFF
            wake_event.set()
            break

    # ----- awake: fake audience -----
    awake = True
    eyes.color = WAKE_COLOR
    print(f"WAKE ({wake_reason}) -- fake audience for "
          f"{AUDIENCE_FAKE_SECONDS:.0f}s (try the button now)")
    time.sleep(AUDIENCE_FAKE_SECONDS)

    # ----- dismiss + cooldown -----
    eyes.off()
    print(f"...audience over, cooling down {REARM_COOLDOWN:.0f}s\n")
    time.sleep(REARM_COOLDOWN)
    with motion_lock:
        motion_spans.clear()      # her own audience's motion doesn't count
    awake = False
