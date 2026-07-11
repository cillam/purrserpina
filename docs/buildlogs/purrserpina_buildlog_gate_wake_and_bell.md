# Purrserpina — Build Log: The Gate, the Wake Logic & the Bell

*Picks up where `purrserpina_buildlog_the_brain.md` left off: brain done (Phase 1),
camera hardware proven with `rpicam-still` but nothing captured from Python yet. This
session got the camera working from Python, built and raced two "is someone there?"
gates, designed the full three-source wake logic, and wired the summon button — with
a Victorian service bell on the way to become its face.*

## Headline
The camera now has a **job**, not just a jack: a fast local person-detector that
gates her wake-up, so the PIR alone no longer decides who gets greeted. Around it,
the whole wake side of the prop got designed and test-scripted: **three wake sources**
(camera-confirmed motion, conservative motion persistence, and a physical summon
button), an ignore-while-awake guard, and the button working on the bench. The gate
race had a clear winner: **local beats cloud, massively, on speed.**

## Camera — from proven hardware to working Python
- **picamera2 was already installed** — it ships preinstalled with full Raspberry Pi
  OS. The import check (`python3 -c "from picamera2 import Picamera2"`) passed clean.
  If it ever needs installing: **apt, not pip** (`sudo apt install python3-picamera2`)
  — it's compiled against the OS's exact libcamera stack, and the pip version breaks.
  One exception to the project's usual `--break-system-packages` habit.
- Caveat noted: apt-installed picamera2 lives in system Python, so it's invisible
  inside a venv unless created with `--system-site-packages`. Not a problem today
  (everything runs system Python) — just a landmine flagged for later.
- `camera_test.py` pattern established: still configuration, `AfMode: 2` (continuous
  autofocus), ~2s settle, capture. IMX708 full stills are 4608×2592; the Wide lens
  fisheyes a little at the edges by design.

## The gate — snap-on-wake, and why
Decision: **she photographs on wake, and the photo decides whether the speaking loop
happens.** This upgrades the old re-trigger plan ("the camera will do this smarter
later") into the wake path itself — one check answers both "was that PIR trigger a
person?" and "has the porch actually cleared?"

- **Fail-open is the law.** If the gate errors or is uncertain, greet anyway — the
  PIR already voted yes. A false greeting to an empty porch is atmosphere; snubbing
  a real kid is a broken prop.
- **The wake photo is not the critique photo.** PIR trips at the edge of range, so
  the wake shot may catch someone mid-approach. The costume-critique shot is a
  *second* snap once the guest is settled (likely at the first question), sent in
  the multimodal `ask_purrserpina` call as planned.

## The gate race — cloud vs local
Built both, same loop, same timing prints, raced head to head:

- **`gate_test.py` (cloud):** snap at 1280×720 → base64 JPEG → Haiku with a
  one-word YES/NO prompt (`max_tokens=5`). Works, but the cost is pure network
  round-trip (~1–2s) — plus pennies per false PIR trigger, which Halloween wind
  would multiply all night.
- **`gate_test_local.py` (local):** snap → MobileNet-SSD (COCO) via TFLite,
  `num_threads=4`, 300×300 input. **Verdict: "soo much faster"** — a few hundred
  ms, no network, no API cost, no WiFi dependency. Prints the best person-confidence
  score, which is the tuning dial (threshold currently 0.50; lower it if real
  people at porch distance score low and empty frames stay near zero).
- **Division of labor settled:** the local model answers "is someone there"
  (dumb, instant, free); **Claude keeps the only job that needs a mind** — the
  costume critique.
- Integration seam: a single `person_present() -> bool` in the brain script, so
  the detector could be swapped without touching anything else. One `Picamera2`
  instance program-wide — the camera can't be opened twice.

## Gotcha: `tflite-runtime` is dead — long live LiteRT
`pip install tflite-runtime` returns *"no matching distribution"* on current Pi OS:
Google stopped updating it and its wheels only ever covered Python ≤3.11. The
successor is **LiteRT**: `pip install --break-system-packages ai-edge-litert`, and
the import becomes `from ai_edge_litert.interpreter import Interpreter` (the script
tries the new name, falls back to the old). The model files are unchanged — same
engine, new package. **Same genus as the pigpio gotcha: Pi tutorials age fast, and
the package the whole internet says to install may be abandoned.** Every TFLite
guide still says `tflite-runtime`; translate it.

Also: the detector needs its model downloaded once (like the Whisper model) —
`coco_ssd_mobilenet_v1_1.0_quant` zip → `~/purr-models/` (`detect.tflite` +
`labelmap.txt`, ~4 MB, offline forever after).

## What the detector can and can't see (masks, dinosaurs)
- **Masks don't matter.** MobileNet's "person" class keys on whole-body shape,
  not faces. Testable at home with a pillowcase/hood/scarf.
- **Body-hiding costumes are the real gap** — inflatable dinosaurs, ghost sheets,
  box robots. Partly proxied with a draped blanket; can't be fully tested until
  real trick-or-treaters exist. The answer isn't a better detector, it's design:
- **The PIR persistence fallback.** PIR and camera are two independent votes. If
  the gate says "no person" but motion is *sustained*, greet anyway — the kid in
  the T-rex suit produces continuous triggers, and the dumb sensor catches what
  the dumb model missed. Failure mode becomes: strange costume → two extra seconds
  of purple-eyed staring → she greets anyway. Reads as her *sensing* rather than
  seeing. Very on-brand.
- The critique photo has no such problem — Haiku recognizes an inflatable
  dinosaur just fine. The weak detector only guards the doorbell, never the fortune.

## Wake arbitration — three sources, one guard (`wake_test.py`)
New test script: PIR + button + eyes only, proving the whole wake design in
isolation before it touches the brain.

1. **Gate-confirmed** — PIR fires, camera says person → wake. (Gate stubbed in the
   test via `GATE_STUB_ANSWER`; rate-limited to one check per 3s so the detector
   doesn't spin on a windy night.)
2. **Persistence** — gate says no, but motion is sustained. Deliberately hard to
   trip (leaves flap in wind): measures **dwell, not triggers** — requires ~5
   cumulative seconds of PIR-high within a 12s window across ≥3 distinct events.
   Any persistence wake then **backs off that path for 4 minutes** (real script:
   only when the greeting gets no reply), so worst case on a windy night is an
   occasional greeting to no one — never a cat yelling at leaves all evening.
   Note: the HC-SR501's hold-time dial inflates dwell — keep it near minimum for
   this to work, sensitivity modest, aimed at the approach path not the bushes.
   Final constants get tuned on the porch (Phase 6), ideally on a breezy evening.
3. **Button** — wakes unconditionally when asleep; a pressed button *is* a person,
   so no gate check. **Ignored while awake or cooling down** (kids will mash it
   mid-audience). "Awake" covers greeting through re-arm.

`wake_reason` is recorded, which opens a flourish: a distinct pre-rendered greeting
per source ("You rang?..." for the button). Test protocol: brisk walk-past = no
wake; stand ~6s = persistence wake; mash button during the purple fake-audience =
IGNORED every time; press while dark = instant wake.

## The button saga (three buttons, one lesson)
- **BOJACK tactile switch:** the plan-of-record wiring — straddle the breadboard's
  center gap (four legs = two internally-joined pairs; the gap forces the circuit
  through the press), one jumper to GPIO 24 (pin 18), one to the ground rail.
- **"Try me" toy buttons: rejected as-is.** Battery-powered means the contacts are
  nodes in a live foreign circuit — wiring the Pi to them merges two circuits: up
  to ~4.5V onto a 3.3V GPIO, no common ground, and the toy's chip fighting the
  Pi's weak (~50kΩ) pull-up. Same rulebook as the servo's 6V rail. Fixable by
  gutting (remove battery, free the switch so it's a **dry contact**) — deferred.
- **What actually got used:** the kit's *pre-wired* button — two wires ending in a
  clip. No breadboard needed at all: the clip goes **straight onto pins 18 + 20**
  (GPIO 24 + the GND right next door), along the outer/even row. Across the rows
  would land on 17+18 (3.3V + GPIO 24) — harmless but dead, since the press would
  connect 3.3V to a pin already held at 3.3V. **Works. Tested.**

### Concept actually learned: a button needs no power
A button isn't a component that *does* anything — it's a gap in a wire. `Button(24)`
enables the Pi's internal pull-up (a whisper of 3.3V from inside the chip); at rest
the pin reads HIGH, a press gives that voltage a path to ground and the pin drops
LOW. The button contributes no energy — which is why it has two connections where
the PIR (which must *generate* a signal) needs three. Also why it wires to ground,
not power. Either wire can be the signal side; buttons have no polarity.

## The bell — the button's real face
Settled plan: a **hotel service bell as the summon button** — ordered: solid brass
Victorian desk bell, 3", ~$15. Period-perfect for a snooty dead aristocrat
(summoning the staff — except the staff is you), and the **ding is instant physical
feedback** during the seconds before her eyes light.

- **Rig plan A:** mount the tactile button inside the hollow base, directly under
  the plunger rod's end-of-travel, so ringing presses it. The bell's own return
  spring gives clean press/release; the bell's mechanical stop absorbs the slams
  so the button only feels the last gentle millimeter. Height/shim is the whole
  trick — set so the rod actuates just before the bell bottoms out.
- **Handling the tiny button: carrier pad.** Glue the button to a coin-sized pad
  of cardboard/wood at the desk first — position and shim the *pad* inside the
  bell, not the speck. Widen the target with a hot-glue dome on the plunger if
  the rod glances off.
- **Rig plan B (if the ornate base is too cramped — a known risk with Victorian
  repros vs plain diner bells):** hinged platform *under* the bell; smacking the
  bell rocks the platform onto a button beneath. Also solves the light bell
  scooting across the table under enthusiastic whacks.
- **Fallback part if the tactile button fights:** a **lever microswitch** (KW12
  type, ~$2) — designed to be smacked by machinery, big forgiving target, C + NO
  terminals wire identically. Deferred-list it.
- **Debounce:** a bell ring is a mechanical shock next to the switch — use
  `Button(24, bounce_time=0.1)`. The ignore-while-awake guard makes chatter
  harmless anyway.
- The bell's physical ding **replaces** the earlier speaker-gong idea — and earns
  the `wake_reason == "button"` line: *"You rang?... How refreshingly presumptuous."*

## Pin map delta
| Signal | GPIO | Physical pin | Notes |
| --- | --- | --- | --- |
| Summon button | GPIO 24 | 18 | was "reserved" — now **in use**; pre-wired clip |
| Button ground | — | 20 | GND next to pin 18; clip spans both |

## Scripts (new this session)
- `gate_test.py` — cloud gate: snap → Haiku YES/NO, timing prints. Kept as fallback.
- `gate_test_local.py` — **the winner**: snap → local MobileNet-SSD person check,
  confidence + timing prints. LiteRT import with tflite-runtime fallback.
- `wake_test.py` — full wake arbitration: three sources, persistence detector,
  backoff, ignore-while-awake guard, fake audience for button-mash testing.
- New deps: `ai-edge-litert` (pip), model files in `~/purr-models/`.
  (`python3-pil` from apt if PIL is missing.)

## Open threads & next steps
1. **Finish the wake_test protocol** if not fully run: walk-past, stand-and-wait,
   button-mash-during-audience, button-while-dark, persistence backoff check.
2. **Tune the local gate** with the score printout: porch distance, edge of frame,
   low light, draped-blanket costume proxy. Adjust `CONFIDENCE` to real margins.
3. **Bell arrives → rig it** (plan A, fall back to B), then re-run the button test.
4. **Merge into the brain:** `person_present()`, the wake arbitration loop, shared
   `Picamera2` instance, per-source greeting lines, `bounce_time` on the button.
5. **Costume-critique integration** (unchanged from last log): second snap at the
   first question → base64 image block in the same Claude call; vision-aware system
   prompt; "critique the costume, never the kid" now load-bearing.
6. **Then the physical build:** into the body, perfboard, porch hardening — where
   the persistence constants get their real values.

*Deadline: Halloween — about four months out. The wake side of her is now designed
end to end; what remains on the bench is merging it into the brain and giving the
camera its second job: judging costumes.*
