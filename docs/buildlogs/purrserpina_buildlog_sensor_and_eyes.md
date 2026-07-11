# Purrserpina Build Log — Motion Sensor & Glowing Eyes

Session goal: resume after a few days, connect to the Pi from my Mac, and get the
motion sensor and the two RGB "eyes" working — first alone, then reacting together.

## What I got working today
- SSH into the Pi from my Mac (no monitor needed)
- HC-SR501 motion sensor wired and detecting motion
- Two RGB LEDs identified as common cathode and wired as a matched pair of eyes
- All three colors confirmed on both eyes
- Eyes change color when the motion sensor triggers

## 1. Connecting to the Pi from my Mac (SSH)
The Pi keeps everything on its SD card between sessions, so nothing was lost.

- Powered up, waited ~1 minute for it to join wifi.
- From the Mac's Terminal: `ssh myusername@purrserpina.local`
- `.local` works on a Mac because macOS has Bonjour built in and Raspberry Pi OS
  answers it. If the name ever fails to resolve, the network may be blocking that
  lookup — fall back to the IP address.
- To find the IP: boot on the monitor once and run `hostname -I`; the first number
  is the address. Then `ssh myusername@192.168.x.x`.

## 2. Motion sensor — HC-SR501
Three male pins under the white dome (order varies by board — trust the labels):
VCC, OUT, GND.

Wiring (sensor pin → Pi):
- VCC → 5V (physical pin 2)
- OUT → GPIO 23 (physical pin 16)
- GND → a ground pin

Note: the cooling fan already occupies pins 4 (5V) and 6 (GND), so the sensor's
ground went to **pin 9** instead. Ground and 5V have duplicates all over the
header, so anything occupied can move to another copy. Signal pins like GPIO 23
are specific and can't be swapped.

Test script — `pir_test.py`:
```python
from gpiozero import MotionSensor
from time import sleep

pir = MotionSensor(23)
print("Warming up, hold still ~30-60 seconds...")
pir.wait_for_no_motion()
print("Ready. Wave your hand.")

while True:
    pir.wait_for_motion()
    print("Motion detected!")
    pir.wait_for_no_motion()
    print("...clear")
```
The sensor needs a 30–60 second warm-up after power and false-triggers during it —
ignore anything it prints until it settles. The two orange dials on the back set
sensitivity and hold-time; left at default for now.

## 3. The eyes — two RGB LEDs
An RGB LED is three LEDs (red, green, blue) in one body, with 4 legs: the three
colors plus one shared "common." The **longest leg is the common**.

Type test (on the breadboard, powered by the MB102 module, not the Pi):
- Put power through a resistor to one leg and ground to another, see which lights.
- Result: powering a **short** leg while the **long** leg went to ground lit it.
  Long leg to ground = **common cathode**. (For common cathode, a color turns on
  when its GPIO pin goes HIGH — the intuitive direction.)

### Getting two eyes down to 4 connections
Wiring each LED independently would be 8 wires to the Pi (3 colors + 1 common,
twice). Instead, both LEDs **share the same three color pins**: the two red legs
land in the same breadboard column, the two greens in another, the two blues in a
third. Both commons go to the shared ground rail.

Result: 3 signal wires + 1 ground = **4 connections**, and both eyes always show
the same color and change together (exactly what's wanted for a matched pair).

Resistors go on the **color legs** (that's where current flows in, for a common
cathode), one 220Ω per color, on the breadboard — so they cost zero Pi pins. Two
LEDs share each color resistor, which makes them glow a little softer (fine for
eyes).

Wiring (after testing on the module, moved to the Pi):
- red → GPIO 17 (physical pin 11)
- green → GPIO 27 (physical pin 13)
- blue → GPIO 22 (physical pin 15)
- both commons → ground rail → one wire to a Pi GND pin

Test script — `eyes_test.py`:
```python
from gpiozero import RGBLED
from time import sleep

eyes = RGBLED(red=17, green=27, blue=22)  # common cathode = default settings

while True:
    eyes.color = (1, 0, 0)   # red
    sleep(1)
    eyes.color = (0, 1, 0)   # green
    sleep(1)
    eyes.color = (0, 0, 1)   # blue
    sleep(1)
```

## 4. Motion + eyes together
First time two parts cooperate: her eyes rest on one color and snap to another
when someone approaches.

`eyes_motion.py`:
```python
from gpiozero import RGBLED, MotionSensor
from signal import pause

eyes = RGBLED(red=17, green=27, blue=22)
pir = MotionSensor(23)

RESTING = (0, 0, 1)   # calm blue
ALERT   = (1, 0, 0)   # red on approach

def someone_here():
    print("Motion — eyes alert")
    eyes.color = ALERT

def all_clear():
    print("Quiet — eyes resting")
    eyes.color = RESTING

eyes.color = RESTING
print("Warming up, hold still ~30-60 seconds...")
pir.wait_for_no_motion()
print("Ready.")

pir.when_motion = someone_here
pir.when_no_motion = all_clear

pause()
```
`when_motion` / `when_no_motion` react the instant the sensor changes (event-driven),
and `pause()` keeps the program alive and listening. Colors are `(red, green, blue)`
values from 0 to 1 — change them to taste. Resting and alert are two of the three
planned states; "consulting the beyond" slots in later when Claude is thinking.

## Pin map so far
| Pin (BCM) | Physical | Use |
| --- | --- | --- |
| 5V | 2 | Sensor VCC |
| 5V | 4 | Fan |
| GND | 6 | Fan |
| GPIO 17 | 11 | Eyes — red |
| GPIO 27 | 13 | Eyes — green |
| GPIO 22 | 15 | Eyes — blue |
| GPIO 23 | 16 | Sensor OUT |
| GND | 9 | Shared ground rail (sensor + eyes commons) |
| GPIO 18 | 12 | **Reserved** for the jaw servo (powered from the cat's battery pack) |
| CSI ribbon | — | Camera — uses **no** header pins |

Plenty of header still free. The camera doesn't compete for GPIO at all.

## Concepts I actually learned (so I don't relearn them)
- **Breadboard:** each column of holes is one connection; columns are separate from
  each other; a gap splits the board top from bottom; the long rails run power and
  ground down the edges. Two things in the same column are wired together.
- **Connector gender:** pins are male, sockets are female. Both the Pi header pins
  and component pins are male, so connecting them needs female ends — or the
  breadboard acts as a junction so two male wire-ends can meet.
- **Common cathode vs anode:** longest leg is common; whichever rail it sits on
  names the type. Long leg to ground = common cathode.
- **Sharing pins:** wiring both LEDs' matching legs into one column makes them act
  as one, cutting 8 connections to 4.
- **Resistor placement:** on the legs current flows through — the color legs, for a
  common cathode.
- **Power/ground consolidation:** one ground wire from the Pi to the breadboard rail
  serves every component's ground. Same idea for power.

## Gotchas hit today
- The Pi header is **male** pins, so male-ended wires can't plug onto it directly —
  needed female ends or the breadboard.
- The fan took pins 4 and 6; moved the sensor ground to another GND pin.
- WAGO connectors are for thick mains wire and can't grab header pins — wrong tool.
- The MB102 power module needs its own power in (USB or a 6.5–12V barrel jack) and a
  voltage jumper set to 3.3V, plus its switch flipped on.

## Reference diagrams (search terms to pull them up again)
- Raspberry Pi 4 GPIO pinout — search "Raspberry Pi 4 GPIO pinout diagram", or use
  **pinout.xyz**
- Breadboard internals — "breadboard how it works power rails rows diagram"
- LED polarity (long/short leg) — "LED anode cathode long leg short leg diagram"
- HC-SR501 sensor pinout — "HC-SR501 PIR motion sensor pinout VCC OUT GND"
- MB102 power module — "MB102 breadboard power supply module 3.3V 5V jumper"
- RGB LED 4-pin pinout — "RGB LED 4 pin common cathode longest leg pinout"
- RGB LED breadboard wiring — "RGB LED breadboard wiring three resistors"

Authoritative docs: pinout.xyz, gpiozero.readthedocs.io, learn.adafruit.com,
learn.sparkfun.com.

## Next session
- Wire and test the jaw servo (GPIO 18, powered from the cat's battery pack) — first
  part that needs separate power.
- Camera when it arrives from CanaKit (CSI ribbon, no GPIO).
- Still need the skeleton itself.
