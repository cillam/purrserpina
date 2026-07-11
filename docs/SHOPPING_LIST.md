# Purrserpina — Shopping List

*Refreshed copy, current as of the servo/voice session. Reflects the settled picks
(MG90S, reused battery pack, confirmed Fyvadio mic and SIMOLIO speaker) and adds a
status column so it's clear what's in hand, tested, on the way, or deferred.*

The prototype build: a talking cat-skeleton on a Raspberry Pi 4 that wakes to motion,
listens, replies in character as Her Infernal Majesty Purrserpina, speaks in a voice,
flaps her jaw to the sound, and (later) sees and critiques costumes.

**Strategy:** buy the cheap, simple version of everything first, get her talking and
reacting end to end, then upgrade only the pieces that testing proves need it.

## Already have
- Raspberry Pi 4 (CanaKit)
- microSD card with Raspberry Pi OS + USB-C power supply (CanaKit)
- Cat skeleton with a movable jaw (plan: remove its motor, drive the jaw with your own servo)
- The cat prop's own 4×AA battery pack (~6V) — reused to power the servo, separate from the Pi

## Buy now — the prototype
| Item | Pick | Rough cost | Status |
| --- | --- | --- | --- |
| Jaw servo | **MG90S** (metal gears, more durable than the SG90) | $3–8 | ✅ have + tested |
| Electronics starter kit | BOJACK 830-point breadboard kit — covers breadboard, jumper wires (incl. male/female), trigger button, plus bonus 5mm + RGB LEDs for her eyes, 220Ω resistors, and 2N2222 transistors | ~$16 | ✅ have + in use |
| USB microphone | Fyvadio omni USB mic | $16–20 | ✅ have + tested clear at a few feet |
| Powered speaker | SIMOLIO, into the Pi's 3.5mm jack | $10–20 | ✅ have + tested |
| PIR motion sensor | HC-SR501 | $3–6 | ✅ have + tested |
| Camera | Raspberry Pi Camera Module 3 **Wide** — CanaKit RSP-CAM-V3-WIDE. 120° lens catches a whole costume at porch distance; genuine Module 3 = standard libcamera, no Arducam driver, ships the right 15-pin cable for the Pi 4 | ~$38 | 🚚 ordered, not arrived |
| A little light | LED candle / lantern / lit "crystal ball" near her — set dressing *and* gives the camera enough to see by | $5–15 | ⬜ pending |
| Stiff wire / linkage | No purchase — a straightened paperclip + the hot glue you have; attach near the *back* of the jaw, close to the hinge | on hand | ⬜ for the mounting phase |

## Deferred — only if testing proves the need
- **Soldered perfboard + 2.54mm screw-terminal blocks** — the permanent wiring upgrade off the
  breadboard for something that survives a night outdoors. (Terminals only pay off soldered to
  perfboard, not plugged into the breadboard; always clamp a wire pigtail, never a bare LED leg.)
- **Ultra-low-light / NoIR camera** — only if the porch is too dark for the Module 3 Wide.
- **Directional or array microphone** — the omni mic tested fine at distance, so this stays parked
  unless a noisy porch on the night proves otherwise.
- **A small screen** — would read the reserved `visual_cue` field; nice-to-have, not core.
- **ElevenLabs voice** — a more theatrical voice than local Piper, if you want the upgrade.

## Accounts & software (free or pay-as-you-go)
- **Anthropic API key** for Claude — her brain; the code uses the fast, cheap Haiku model.
- **Text-to-speech:** `espeak-ng` working now as a stand-in; **Piper** (free, local) is the planned
  real voice; ElevenLabs later if desired.
- **Speech-to-text:** still to choose — a cloud endpoint (fast, needs WiFi) or `faster-whisper`
  (offline, slower on a Pi 4).

## Still needed to finish the physical build
- The little light (above), whenever convenient.
- Camera to arrive, then bench-test it like the mic (`libcamera-hello` / a still capture).
- Mounting consumables already on hand: hot glue, paperclip linkage; optional perfboard + terminals
  when you commit to the permanent build.
