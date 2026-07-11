# Purrserpina — Build Log: Servo, Voice & the Full Loop

*Picks up where `purrserpina_buildlog_sensor_and_eyes.md` left off. That log ended
with the sensor and eyes working and the servo as the next session. This one covers
the jaw servo, her voice, and the first end-to-end motion → listen → speak → jaw loop.*

## What's working now

The whole spine of the prop runs end to end on the breadboard:

- **Motion wakes her** — the PIR trips, the eyes light and *stay* on.
- **She "hears"** — a volume threshold on the USB mic stands in for real listening.
- **She speaks** — a fixed line via espeak-ng, played through the speaker.
- **Her jaw moves in time with the speech** — it flaps while the audio plays, then
  closes and goes still the instant it ends.

All five core parts (motion sensor, RGB eyes, mic, speaker, jaw servo) now act as one
behavior. That's Layer 1 of the original plan done, and Layer 2 half-done — she has a
voice, but not yet a real brain.

## Hardware added this stretch — the jaw servo

- **Servo:** MG90S. Three wires: **brown = ground, red = power, yellow = signal.**
- **Signal → GPIO 18 (physical pin 12)** — the Pi's hardware-PWM pin, the good one for a servo.
- **Power: its own supply, never the Pi's 5V.** Bench-tested first off the MB102 module
  (rail set to 5V), then moved to the **4×AA battery pack (~6V)** — the real setup.
- **Common ground is mandatory:** the servo's brown, the battery −, and a wire to a Pi
  GND pin all sit in one rail. (Why, below.)
- The servo came with a prewired **female** connector, so male jumpers go into the three
  sockets and out to their destinations.

## Updated pin map

| Signal | GPIO | Physical pin | Notes |
| --- | --- | --- | --- |
| Eyes – red | GPIO 17 | 11 | RGB common-cathode; **both eyes share these three lines** |
| Eyes – green | GPIO 27 | 13 | 220Ω on each color leg |
| Eyes – blue | GPIO 22 | 15 | commons → ground rail |
| PIR OUT | GPIO 23 | 16 | VCC → 5V (pin 2), GND → pin 9 |
| Cooling fan | — | 4 (5V) + 6 (GND) | took those pins first |
| Servo signal | GPIO 18 | 12 | yellow wire |
| Servo power | — | battery + | red wire — **battery is on the + rail only** |
| Servo ground | — | battery − → Pi pin 14 | brown wire; pin 14 is free and sits next to pin 12 |

Speaker: SIMOLIO on the 3.5mm analog jack (output set to **Analog**, not HDMI).
Mic: Fyvadio omni USB. Camera: CSI Module 3 — **not arrived yet.**

## Concepts I actually learned (so I don't relearn them)

- **Why a separate ground wire runs from the breadboard to the Pi.** Voltage is always
  measured *relative to a zero*. The battery and the Pi each have their own idea of zero.
  The signal wire means "3.3V above the Pi's zero," but the servo can only read it against
  *its* zero (the battery's). Tie the two grounds together and they share one zero, so the
  pulse reads correctly. Power can come from one source and signal from another — but
  ground must be common. No common ground = the servo twitches or sits dead.
- **Any Pi ground pin works.** All eight (pins 6, 9, 14, 20, 25, 30, 34, 39) are internally
  one node. Pick whichever free one is a convenient reach.
- **6V must never touch a 3.3V line.** Only the servo's red goes on the battery + rail. 6V
  onto a GPIO pin or an LED leg can fry the Pi — the one wiring mistake here with real teeth.
- **Servo PWM jitter.** The default GPIO library (lgpio) makes the holding pulse in software,
  so it wobbles and the servo hunts — the constant idle twitch. For a jaw that rests then
  chomps, the fix isn't steadier pulses, it's **`detach()`**: stop sending a pulse at rest
  and the jaw goes silent and still.
- **The talking-jaw trick (no lip-sync).** Play the audio in the *background* and flap the
  jaw open/shut until the playback process ends. The mouth auto-matches the line's length.
  This is exactly what the ChatterPi tool does — I just built it myself.
- **Arduino → gpiozero color translation.** `analogWrite` 0–255 maps to gpiozero's `color`
  0.0–1.0 (divide by 255). Common-cathode means *no* value inversion (full value = full
  brightness). PWM is on by default, so blended colors (yellow/purple/aqua) just work. Both
  eyes share the three pins, so they always show the same color.
- **"Hearing" right now is volume, not words.** It triggers on any loud-enough sound, not
  the word "hello." A deterministic stand-in until real speech-to-text goes in — the
  structure won't change when it does.

## Gotchas hit (and how they were solved)

- **`pigpio` won't install** — "no installation candidate." The newest Raspberry Pi OS
  dropped it from the repos. Fix: don't use it; the `detach()` approach removes the need.
- **`python3-sounddevice` isn't in apt.** Installed `sounddevice` via
  `pip install --break-system-packages sounddevice`, plus `libportaudio2` from apt —
  PortAudio is the C library underneath, without which the mic call errors.
- **apt is all-or-nothing.** One unfindable package name makes the whole `apt install`
  line install *nothing*. Split the findable ones (`espeak-ng python3-numpy libportaudio2`)
  from the pip one.
- **`aplay` is flaky on this OS / PipeWire.** Play through `ffplay` instead — it routes the
  normal way. (espeak-ng writes a `.wav`, then ffplay plays it.)
- **`arecord -l` vs `-1`** — that's a lowercase **L** (list), not a one.
- **Servo sat still while everything else worked** — check the battery pack is switched
  **on**, then check the common ground to pin 14.

## LED-in-skull mounting — decisions captured for the mounting phase

*(Not done yet — waiting on the skeleton. Notes so I don't re-derive them.)*

- Keep the resistors and breadboard at the base; run only thin wires up to the eye sockets.
  Resistors never go in the socket.
- **Insulate each LED leg** (heat-shrink, or tape wrapped one leg at a time) — close-spaced
  legs touching is the real risk. Heat is *not* a risk at 220Ω, so hot glue is safe.
- **Diffuse each LED** (ping-pong ball, frosted bead, hot-glue blob, or cotton) so the whole
  socket glows like an eye, and mount it from *behind* the socket.
- **Strain-relief** the wire inside the skull so a tug can't rip a leg joint.
- **Female jumpers** push onto LED legs fine (the legs act like male pins) and their housings
  insulate; the weakness is grip, so tape or glue to lock once placement looks right.
- **Re-run the three-color test after mounting** — bending and gluing is exactly when a
  connection breaks.

## The permanent upgrade (when she goes in the body)

The breadboard's friction contacts and the tall, floppy, bare-legged resistors are fine for
the bench but not for a night outdoors. For now: **trim the resistor legs short and bend them
flat, keep the three parallel and spaced** so bare legs can't touch. The real fix later is a
**soldered perfboard** — resistors lie flat, no exposed bridging — with **screw-terminal
blocks** (the 2.54mm PCB-mount set) as the points where the eye and servo wires screw in.
Note: those terminals only pay off *soldered to perfboard*, not plugged into the breadboard
(otherwise the flaky breadboard contact is still in the chain), and always clamp a wire
pigtail, never a bare LED leg.

## Current scripts

**`talk_test.py`** — the full loop: motion → eyes → listen → speak → jaw.

```python
import subprocess
import numpy as np
import sounddevice as sd
from gpiozero import MotionSensor, RGBLED, Servo
from time import sleep

pir  = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
jaw  = Servo(18)
jaw.detach()                # start limp + silent, no idle twitch

THRESHOLD  = 0.05           # mic volume that counts as "heard you" — tune this
SAMPLERATE = 44100
CHUNK      = 0.3

MOUTH_SHUT = -0.3           # jaw positions while talking — re-tune once mounted
MOUTH_OPEN =  0.3
FLAP       = 0.13           # seconds per open/shut — smaller = chattier

def mic_level():
    audio = sd.rec(int(CHUNK * SAMPLERATE), samplerate=SAMPLERATE,
                   channels=1, dtype="float32")
    sd.wait()
    return float(np.sqrt(np.mean(audio ** 2)))

def say(text):
    """Speak a line while flapping the jaw in time with the audio."""
    subprocess.run(["espeak-ng", "-v", "en-us+f3", "-s", "140", "-p", "35",
                    "-w", "/tmp/purr.wav", text])
    player = subprocess.Popen(["ffplay", "-autoexit", "-nodisp",
                               "-loglevel", "quiet", "/tmp/purr.wav"])
    while player.poll() is None:        # flap until the audio ends
        jaw.value = MOUTH_OPEN
        sleep(FLAP)
        jaw.value = MOUTH_SHUT
        sleep(FLAP)
    jaw.value = MOUTH_SHUT
    sleep(0.3)
    jaw.detach()

print("Purrserpina sleeps. Walk up to wake her. (Ctrl+C to stop)\n")

while True:
    pir.wait_for_motion()
    eyes.color = (0.4, 0, 0.5)          # dim purple — she stirs, stays lit
    print("Someone's there... her eyes open. Say hello.")

    while True:
        level = mic_level()
        print(f"   listening... level={level:.3f}")
        if level >= THRESHOLD:
            break

    print("She heard you.")
    eyes.color = (1, 0, 0)              # eyes flare red
    say("Ahh. A visitor. I have been expecting you. Sit, and I shall read your fate.")

    eyes.off()
    print("...she sinks back into the dark.\n")
```

**`color_test.py`** — cycles the eyes through six colors; good for confirming all three
channels work and eyeballing which colors read well through the diffusers.

```python
from gpiozero import RGBLED
from time import sleep

eyes = RGBLED(red=17, green=27, blue=22)

def set_color(red, green, blue):          # keep the familiar 0–255 scale
    eyes.color = (red / 255, green / 255, blue / 255)

while True:
    set_color(255, 0, 0);   sleep(1)      # red
    set_color(0, 255, 0);   sleep(1)      # green
    set_color(0, 0, 255);   sleep(1)      # blue
    set_color(255, 255, 0); sleep(1)      # yellow
    set_color(80, 0, 80);   sleep(1)      # purple
    set_color(0, 255, 255); sleep(1)      # aqua
```

*(Also on the Pi: `servo_test.py`, the original min/mid/max sweep, and
`purrserpina_test.py`, the no-jaw version of the loop.)*

## Next steps

The critical path is pure software and needs nothing in the mail.

1. **Phase 1 — The brain (next up).** Wire her to the Claude API (the cheap, fast Haiku
   model) with the in-character, child-safe system prompt. Shape replies as JSON with the
   reserved `visual_cue` field. Swap the fixed line for a generated fortune, and keep the
   jaw flapping on the result. Still fired by the volume trigger for now. *Done when she
   says something different and in character every time.*
2. **Phase 2 — Real ears.** Replace the volume trigger with speech-to-text so she answers
   *what was said*. Settle the open fork here: cloud STT (fast, needs WiFi) vs faster-whisper
   (offline, slower). *Done when she answers your actual words.*
3. **Phase 3 — Better voice (optional, anytime).** Swap espeak-ng for Piper — free, local,
   far less robotic. Independent of everything else, so drop it in whenever.
4. **Phase 4 — Costume vision (camera-gated).** When the Module 3 arrives from CanaKit:
   test it like the mic, then fold a photo into the *same* Claude call that writes her
   reply. CSI ribbon, no GPIO to fight. Blocks nothing else.
5. **Phase 5 — Into the body (needs the skeleton).** Off the breadboard and into the cat:
   LEDs seated in the sockets, servo linked to the real jaw, parts placed, perfboard upgrade.
6. **Phase 6 — Porch hardening (nearer October).** Real distance + noise testing, lighting
   for the camera, outdoor power and weather, full dress rehearsal.

Deadline is Halloween — about four months out — so this is sessions, not a sprint.
**Immediate move: Phase 1 — the API hookup and her system prompt.**
