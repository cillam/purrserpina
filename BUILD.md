# Purrserpina — Build Plan

*The master design doc, refreshed after the wake-arbitration session (log 08). The
numbered build logs in `docs/buildlogs/` tell the story session by session; this file is
the current truth.*

**The build:** a talking cat-skeleton on a Raspberry Pi 4 that wakes when someone
approaches, grants them three questions, has Claude write each reply in character, speaks
it aloud, and moves her jaw in time with the sound.

**The character:** Her Infernal Majesty Purrserpina — a dead, snooty, fortune-telling
aristocrat cat who finds Halloween beneath her and shows up anyway. (A pun on Proserpina,
queen of the underworld.)

## Architecture decisions (the real ones)

- **Brain = Claude Haiku in the cloud.** The Pi 4 can't run a language model at usable
  speed. The round-trip's lag would ruin a kitchen assistant but *reads as atmosphere* on a
  fortune teller who pauses to consult the beyond.
- **Multi-turn, bounded audience.** The API is stateless, so memory is a `messages` list
  resent each turn and wiped on re-arm — no visitor inherits another's conversation. She
  grants **three questions** as ancient law, then dismisses.
- **Rules live in code, not the prompt.** The model miscounts and folds to "one more", so
  code owns every limit: the three-question cap (a stage direction on the final turn tells
  her to dismiss), the once-per-visitor costume exchange, the persistence backoff. The
  prompt owns only the *flavor*. Same principle for output hygiene: `clean_for_speech()`
  strips asterisks and markdown rather than trusting the prompt to prevent them.
- **Replies are plain prose.** The old JSON-with-`visual_cue` design is deferred until a
  screen exists; prose made sentence-streaming simple.
- **Three wake sources, one guard.** PIR motion never wakes her alone:
  1. **Gate** — PIR fires and an on-device person detector (MobileNet-SSD, ~0.1–0.2 s) sees a person.
  2. **Persistence** — the gate says no but motion is *sustained* (dwell, not triggers), which
     catches body-hiding costumes like inflatable dinosaurs.
  3. **Button** — the summon bell; a press *is* a person, so no gate check.
  Priority while asleep: button > gate > persistence (a ring during a gate check wins). The
  button is ignored from the wake decision through the end of re-arm.
- **Fail-open is the law.** Any gate error, missing camera, or missing model means greet
  anyway — a false greeting to an empty porch is atmosphere; snubbing a real kid is a broken prop.
- **Escalating persistence backoff.** A persistence wake nobody answers was probably wind:
  she says "*Hm. Only the wind, then.*" and rests that path 60 s, doubling per consecutive
  wind wake to a 240 s cap, reset the moment anyone answers her. Gate and button stay live.
- **Per-source greetings.** Each wake source has its own opener ("You rang?... How
  refreshingly presumptuous." for the bell) plus one shared terms line, pre-rendered as one wav.
- **Ask, don't look.** The camera's only job is the local gate; frames never leave the Pi.
  Costume vision was designed and then **dropped for privacy** (photos of children would sit
  on Anthropic's servers up to 30 days). Instead, if a guest opens with small talk, Haiku
  flags it with a `[COSTUME]` tag and asks what creature they've come as; code strips the
  tag, refunds the question, and makes their answer a free turn — once per visitor, first
  utterance only. A per-event **sight mode** is deferred (design below).
- **The jaw follows the voice.** Amplitude-driven: each wav's loudness envelope (normalized
  to the 90th-percentile speech level) drives the servo, synced by wall-clock time. No lip-sync.
- **Latency is theater.** Pre-rendered stall line + ambience bed + "channeling" SFX and
  eye-storm, while the reply is synthesized **sentence by sentence** on a producer/consumer
  queue so playback starts the instant sentence one is ready.
- **Listens only when prompted**, so her speaker never bleeds into the mic. A stray blip
  that starts a recording but proves too quiet to be speech is discarded, and she keeps
  listening for the rest of the begin-wait instead of ending the turn.
- **Child-safe guardrails in her system prompt:** she critiques the *costume* (as described,
  aimed at the creature chosen, never effort or cost), never the child; grace for no costume
  or homemade ones; asks nothing about who a child really is; if a child sounds scared she
  drops the disdain and reassures; she gives no real-world advice.
- **Privacy by construction:** nothing about a guest is written to disk on the Pi; audio is
  transcribed locally; only conversation *text* goes to the API (commercial terms: no
  training, deleted within 30 days barring flagged-content/legal exceptions). See the
  README's Privacy section.

## The pipeline

```
PIR ──► local person gate ──┐
  └─ sustained motion ──────┼──► wake (wake_reason: gate | persist | button)
bell ───────────────────────┘          │
                                       ▼
   greeting for that wake_reason (pre-rendered)
                                       ▼
   × up to 3 questions (+ one free costume exchange if they open with small talk):
       eyes pulse green -> record until quiet (false starts discarded)
       -> faster-whisper tiny.en (offline) -> transcript
       -> stall line + ambience  |  Claude Haiku reply (background thread)
       -> channeling SFX + eye-storm
       -> Piper, sentence by sentence, jaw tracking loudness
                                       ▼
   dismissal -> dark -> wait for porch to clear + cooldown -> re-arm, memory blank
```

## Pin map (current)

| Signal | GPIO | Physical pin | Notes |
| --- | --- | --- | --- |
| Eyes – red | GPIO 17 | 11 | RGB common-cathode; **both eyes share these three lines** |
| Eyes – green | GPIO 27 | 13 | 220Ω on each color leg |
| Eyes – blue | GPIO 22 | 15 | commons → ground rail |
| PIR OUT | GPIO 23 | 16 | VCC → 5V (pin 2), GND → pin 9 |
| Cooling fan | — | 4 (5V) + 6 (GND) | took those pins first |
| Jaw servo – signal | GPIO 18 | 12 | hardware-PWM pin; yellow wire |
| Jaw servo – power | — | battery + | red wire — **battery on the + rail only** |
| Jaw servo – ground | — | battery − → Pi pin 14 | brown wire; common ground |
| Summon button | GPIO 24 | 18 | pre-wired clip; `bounce_time=0.1` |
| Button ground | — | 20 | GND next to pin 18; the clip spans both |
| Camera | — | CSI ribbon | Module 3 Wide (IMX708); no header pins. **Not hot-pluggable.** |

Speaker: SIMOLIO on the 3.5mm analog jack (output set to **Analog**, not HDMI).
Mic: Fyvadio omni USB (48 kHz only — downsampled 3:1 to 16 kHz for Whisper).

## Power & wiring notes

- **The servo has its own supply** (the reused 4×AA pack, ~6V) — never the Pi's 5V, because
  a servo's current spikes would dip the Pi's rail and reboot it.
- **Common ground is mandatory:** servo brown + battery − + a wire to a Pi GND (pin 14) share
  one rail, so the signal has a shared zero. No common ground = twitch/dead.
- **6V must never touch a 3.3V line.** Only the servo's red sits on the battery + rail.
- **Never wire the Pi into a battery-powered toy button** — its contacts are live nodes in a
  foreign circuit. A button must be a dry contact (gutted, or the kit tactile switch).
- **Permanent build (later):** soldered perfboard with screw-terminal blocks; clamp wire
  pigtails, never bare LED legs.

## Software stack

- **GPIO:** `gpiozero` (default `lgpio` backend). `Servo.detach()` at rest kills idle jitter.
- **Brain:** `anthropic` SDK, `claude-haiku-4-5`. Key in `~/.purrserpina.env` (`chmod 600`,
  outside the repo), sourced from `~/.bashrc`; systemd `EnvironmentFile=` when she becomes a service.
- **Ears:** `faster-whisper` `tiny.en`, int8, `beam_size=1`, `vad_filter=True`.
- **Voice:** Piper `en_US-kristin-medium` (volume 1.0, length_scale 1.2, noise 0.667 / 0.8). Playback via `ffplay`.
- **Vision gate:** `picamera2` (**apt**, not pip) + MobileNet-SSD COCO on LiteRT (`ai-edge-litert`).
- **Workflow:** edit on the Mac → `purr-deploy` (git push + Pi `git pull --ff-only`). The Pi's
  copy is never edited directly. `prompts/system_prompt.md` is versioned separately.

## Gotchas learned (so they don't bite again)

- `pigpio` is gone from the newest OS repos — don't use it.
- `python3-sounddevice` isn't in apt → pip `sounddevice`, plus `libportaudio2` from apt.
- `apt install` is all-or-nothing — one unfindable name aborts the whole line.
- `aplay` is flaky on this OS/PipeWire → play via `ffplay`.
- `tflite-runtime` is dead → `ai-edge-litert`, import `ai_edge_litert.interpreter`.
- `picamera2` from **apt**; it's invisible inside a venv unless created with `--system-site-packages`.
- Newest Pi OS camera tools are `rpicam-*`, not `libcamera-*`.
- **The COCO labelmap's first row is `???`.** The model numbers classes from 0 (0 = person);
  strip the placeholder first or "person" lands on index 1 (bicycle) and the gate scores
  0.00 forever. (Lost once in a "paths-only" rewrite — log 08.)
- picamera2's `"BGR888"` format yields **RGB-ordered** arrays. Don't "fix" it.
- Setting `eyes.color` does **not** stop a running `pulse()` thread — `eyes.off()` first.
- scp/ssh need `purrserpina.local`; `hostname -I` gives the IP fallback.
- Heredocs: `EOF` on its own line, or the file is silently garbage.
- Assets are gitignored and don't ride `purr-deploy`; Piper needs the `.onnx.json` sidecar too.

## Status

**Done:** amplitude jaw · Piper voice · offline ears · Claude brain + three-question audience ·
latency masking · repo + deploy pipeline · wake arbitration merged into the brain (three
sources, fail-open gate, escalating backoff, per-source greetings, wind line) · false-start
handling in `record()` · "ask, don't look" costume talk · privacy section in the README.

**In progress:** on-Pi smoke test of the merged brain, then the full wake-test protocol.

## Next steps

1. **Wake-test protocol** (`purrserpina_brain.py`, `GATE_MODE` as needed):
   brisk walk-past = no wake · stand ~6 s with `GATE_MODE="stub_no"` = persistence wake ·
   mash the bell mid-audience = `IGNORED` every time · ring while dark = instant "You rang?" ·
   ring within a second or two of the PIR tripping = button greeting, not gate · second
   stand-and-wait within 60 s of an unanswered persistence wake = refused · open with
   "trick or treat!" = costume question, question refunded.
2. **Gate tuning** with real scores: porch distance, frame edges, low light, a draped-blanket
   costume proxy. Adjust `CONFIDENCE` (0.50) to the real margins.
3. **Bell rig** when it arrives (plan A: switch under the plunger; plan B: hinged platform;
   fallback part: KW12 lever microswitch). The little light.
4. **Into the body:** LEDs in the sockets, servo linked to the real jaw (re-tune
   `MOUTH_OPEN`/`MOUTH_SHUT`, A/B against `JAW_MODE="flap"`, watch for buzz), mic/speaker/
   camera placement, perfboard with screw terminals.
5. **Porch hardening:** persistence constants on a breezy evening (HC-SR501 hold-time dial
   near minimum); lingering-kid re-greet vs `COOLDOWN`; outdoor power and weather; **systemd
   service** with `EnvironmentFile=`, an API spend cap, and transcript printing disabled or
   a non-persistent journal (otherwise a night of kids' questions lands in the log on disk);
   dress rehearsal.

**Deferred / optional (after Halloween unless time appears):**
- **Sight mode** (see below).
- A small screen reading a revived `visual_cue` field.
- Voice effects via `pedalboard`; ElevenLabs if she wants more theater.
- Steady-green listen instead of a pulse (kills the pulse→red flicker class of bug).
- Continuous PCM playback if between-sentence `ffplay` gaps ever grate.

## Sight mode — design captured, not built

An optional, **per-event** return of costume vision, for settings where it fits (an adult
party where everyone knows a camera is in use). **Off by default; chosen by the host, never
by her** — no automatic age estimation from the camera, ever.

- **Switch:** a hidden GPIO toggle read at startup (change mode on the night without a laptop),
  or a `--sight` flag. Startup banner announces the mode; a distinct boot eye-flash in sight mode.
- **Prompt:** move the sight-specific lines out of `system_prompt.md` into `prompts/blind.md`
  and `prompts/sight.md`; code appends the one matching the mode. Lore: on certain nights the
  veil thins and her sight returns. `sight.md` carries the vision guardrails — the costume only,
  never anything that's part of the person; ask rather than guess; never mention a bad image;
  address groups by their costumes.
- **Flow:** snap at the guest's first utterance via the shared `capture_frame()`, attach as a
  base64 image block to that first message only (it stays in history for later riffs). The
  small-talk costume question is skipped — she can see. Fail-open: no camera = blind mode for
  that guest. The photo is never written to disk on the Pi.
- **Docs:** README Privacy gains a sight-mode subsection (one photo per visitor to the API,
  up to 30 days retention) before it ships.

## Repo layout

```
purrserpina_brain.py      the animatronic — single entry point
prompts/system_prompt.md  her character, versioned separately
tests/                    bench scripts: eyes, servo, mic, camera, gate_test_local,
                          gate_diag, wake_test, voice_test, ears_test_piper
docs/BUILD.md             this file
docs/SHOPPING_LIST.md     parts, status, deferred list
docs/buildlogs/           01–07 (+ 08: wake merge, gate fix, privacy, ask-don't-look)
assets/                   gitignored — voices, models, sounds (see README manifest)
```

*Deadline: Halloween — ~26 days out. The software is nearly done; the body is the
remaining risk.*
