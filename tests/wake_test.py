#!/usr/bin/env python3
"""Bench test: wake arbitration — three sources, one guard. No brain, no camera.

Sources (in priority order while asleep):
  1. gate     — PIR fires and the camera gate says person. STUBBED here via
                GATE_STUB_ANSWER so this test needs no camera; rate-limited so
                a windy night can't spin the detector.
  2. persist  — gate says no, but motion is SUSTAINED. Measures dwell, not
                triggers: ~5 cumulative seconds of PIR-high inside a 12s
                window, across >= 3 distinct events. Deliberately hard to trip
                (leaves flap in wind). Any persistence wake backs that path
                off for 4 minutes.
  3. button   — the summon bell (GPIO 24). A pressed button IS a person, so it
                wakes unconditionally when asleep — and is IGNORED while awake
                or cooling down (kids WILL mash it mid-audience).

Test protocol (from log 05):
  - brisk walk-past                    -> NO wake (stub set to "no")
  - stand in view ~6s                  -> persistence wake
  - mash button during the fake audience -> "IGNORED" printed every time
  - press button while dark            -> instant wake, "You rang?" line
  - second stand-and-wait within 4 min -> persistence path refuses (backoff)

Set GATE_STUB_ANSWER = "yes" to exercise the gate-confirmed path instead.

Run from anywhere:  python3 tests/wake_test.py
Reminder: keep the HC-SR501 hold-time dial near MINIMUM or it inflates dwell.
"""
import time
from threading import Lock

from gpiozero import MotionSensor, RGBLED, Button

# --- config -------------------------------------------------------------------
GATE_STUB_ANSWER = "no"      # "yes" | "no" | "error"  (error must fail-open)
GATE_MIN_INTERVAL = 3.0      # seconds between gate checks

PERSIST_WINDOW = 12.0        # look-back window (s)
PERSIST_DWELL = 5.0          # cumulative PIR-high seconds required inside window
PERSIST_EVENTS = 3           # distinct motion events required inside window
PERSIST_BACKOFF = 240.0      # after a persistence wake, that path sleeps (s)

AUDIENCE_SECONDS = 10.0      # fake audience — stands in for the real conversation
COOLDOWN = 3.0               # after the porch clears, before re-arm

WAKE_COLOR = (0.4, 0, 0.5)   # purple, same as the brain's wake state

GREETINGS = {
    "gate": "A visitor... I have been expecting you.",
    "persist": "I sense... something. Show yourself.",
    "button": "You rang?... How refreshingly presumptuous.",
}

# --- hardware -------------------------------------------------------------------
pir = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
button = Button(24, bounce_time=0.1)   # bell ring = mechanical shock; debounce it

# --- shared state ------------------------------------------------------------------
state_lock = Lock()
awake = False                 # covers greeting through re-arm (incl. cooldown)
button_requested = False      # set by the callback, consumed by the main loop
motion_events = []            # list of [start_time, end_time_or_None]
last_gate_check = 0.0
persist_backoff_until = 0.0


# --- PIR bookkeeping: record intervals, judge dwell later ----------------------------
def on_motion():
    with state_lock:
        motion_events.append([time.monotonic(), None])


def on_no_motion():
    with state_lock:
        if motion_events and motion_events[-1][1] is None:
            motion_events[-1][1] = time.monotonic()


pir.when_motion = on_motion
pir.when_no_motion = on_no_motion


def on_button():
    global button_requested
    with state_lock:
        if awake:
            print("   button IGNORED (awake / cooling down)")
        else:
            button_requested = True


button.when_pressed = on_button


# --- the gate (stub) --------------------------------------------------------------
def person_present() -> bool:
    """Stub for the camera gate. Fail-open is the LAW: on error, the PIR
    already voted yes — greeting an empty porch is atmosphere; snubbing a
    real kid is a broken prop."""
    if GATE_STUB_ANSWER == "yes":
        return True
    if GATE_STUB_ANSWER == "no":
        return False
    print("   gate error -> fail-open, treating as person")
    return True


# --- persistence math -----------------------------------------------------------------
def persistence_met() -> bool:
    """Dwell, not triggers: cumulative PIR-high seconds and distinct events
    inside the look-back window."""
    now = time.monotonic()
    window_start = now - PERSIST_WINDOW
    dwell = 0.0
    events = 0
    with state_lock:
        for start, end in motion_events:
            e = end if end is not None else now      # still-open interval
            s = max(start, window_start)
            if e > s:
                dwell += e - s
                events += 1
    return dwell >= PERSIST_DWELL and events >= PERSIST_EVENTS


def prune_events():
    """Drop intervals that ended before the look-back window (keep the list tiny)."""
    cutoff = time.monotonic() - PERSIST_WINDOW
    with state_lock:
        motion_events[:] = [ev for ev in motion_events if ev[1] is None or ev[1] > cutoff]


# --- the fake audience --------------------------------------------------------------
def hold_fake_audience(reason: str):
    global awake, button_requested, persist_backoff_until
    with state_lock:
        awake = True
        button_requested = False

    print(f"\n*** WAKE (wake_reason = {reason}) ***")
    print(f'    "{GREETINGS[reason]}"')
    eyes.color = WAKE_COLOR
    print(f"    ...fake audience for {AUDIENCE_SECONDS:.0f}s — mash the button now, "
          "it must print IGNORED...")
    time.sleep(AUDIENCE_SECONDS)

    eyes.off()
    print("    audience over. Waiting for the porch to clear...")
    pir.wait_for_no_motion()
    time.sleep(COOLDOWN)

    if reason == "persist":
        persist_backoff_until = time.monotonic() + PERSIST_BACKOFF
        print(f"    persistence path backing off {PERSIST_BACKOFF:.0f}s")
        # (real script: back off only when the greeting gets no reply)

    with state_lock:
        awake = False
        button_requested = False
        motion_events.clear()
    print("    re-armed, memory blank.\n")


# --- main loop ------------------------------------------------------------------------
print("Wake test armed. Sources: gate(stub={}) | persistence | button. Ctrl+C to stop.\n"
      .format(GATE_STUB_ANSWER))
print("Warming up the PIR — hold still ~30-60s, ignore anything it prints...")
pir.wait_for_no_motion()
print("Ready.\n")

try:
    while True:
        # 1) button — a press IS a person
        with state_lock:
            pressed = button_requested
        if pressed:
            hold_fake_audience("button")
            continue

        # 2) PIR-driven paths
        if pir.motion_detected:
            now = time.monotonic()
            if now - last_gate_check >= GATE_MIN_INTERVAL:
                last_gate_check = now
                t0 = time.time()
                seen = person_present()
                print(f"PIR high -> gate check: {'person' if seen else 'no person'} "
                      f"({time.time() - t0:.2f}s)")
                if seen:
                    hold_fake_audience("gate")
                    continue

            # gate said no (or was rate-limited): consider persistence
            if time.monotonic() >= persist_backoff_until and persistence_met():
                hold_fake_audience("persist")
                continue

        prune_events()
        time.sleep(0.1)
except KeyboardInterrupt:
    eyes.off()
    print("\nStopped.")
