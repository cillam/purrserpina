# Purrserpina — Build Plan

*Refreshed copy, rebuilt from the project history and current as of the servo/voice
session. The master design doc; the session build logs sit alongside it.*

**The build:** a talking cat-skeleton on a Raspberry Pi 4 that wakes to motion, listens
to a trick-or-treater, has Claude write a reply in character, speaks it aloud, and moves
her jaw in time with the sound — and, once the camera's in, glances at the costume too.

**The character:** Her Infernal Majesty Purrserpina — a dead, snooty, fortune-telling
aristocrat cat who finds Halloween beneath her and shows up anyway. (A pun on Proserpina,
queen of the underworld.)

## Architecture decisions (the real ones)

- **Brain = Claude in the cloud, the fast/cheap Haiku tier.** The Pi 4 is too weak to run a
  language model locally at usable speed. The cloud round-trip's lag would ruin a kitchen
  assistant but *reads as atmosphere* on a fortune teller who pauses to consult the beyond.
- **Costumes via one multimodal call.** When the camera's in, she sends a photo to Claude in
  the *same* request that writes her reply — image and dialogue together, no separate vision model.
- **No lip-syncing.** The jaw servo opens in proportion to how loud the audio is at each
  moment, which reads as speech without any phoneme analysis. (Already built — see the loop.)
- **Replies as structured JSON**, with a reserved `visual_cue` field that's ignored today so a
  screen can be added later without rewriting the loop.
- **Listens only when prompted**, so her own speaker never bleeds into the mic — no
  echo-cancellation hardware needed.
- **Child-safe guardrails in her system prompt:** she critiques the *costume*, never the kid
  wearing it; if a child sounds scared she drops the disdain and reassures; she stays in
  character and gives no real-world advice.

## The pipeline

```
motion (or button) wakes her
   -> record the guest (mic)
   -> speech-to-text                      [TODO: pick cloud vs faster-whisper]
   -> Claude (Haiku) returns JSON: {"speech": ..., "visual_cue": ...}
   -> text-to-speech writes a .wav
   -> jaw servo flaps to the .wav's loudness while it plays
   (visual_cue is ignored today; a screen will read it later)
```

The reply is requested as **JSON only**: `{"speech": "<spoken reply>", "visual_cue": "<short
tag or empty>"}`. The `speech` field is read aloud, so it must be plain spoken words — no
symbols, stage directions, or emoji.

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
| Button (optional) | GPIO 24 | 18 | hidden manual trigger, if used |

Speaker: SIMOLIO on the 3.5mm analog jack (output set to **Analog**, not HDMI).
Mic: Fyvadio omni USB. Camera: CSI Module 3 Wide — **not arrived yet.**

## Power & wiring notes

- **The servo has its own supply** (the reused 4×AA pack, ~6V) — never the Pi's 5V, because a
  servo's current spikes would dip the Pi's rail and reboot it.
- **Common ground is mandatory:** servo brown + battery − + a wire to a Pi GND (pin 14) share one
  rail, so the signal has a shared zero to be measured against. No common ground = twitch/dead.
- **6V must never touch a 3.3V line.** Only the servo's red sits on the battery + rail; 6V onto a
  GPIO pin or LED leg can fry the Pi.
- **Permanent build (later):** move off the breadboard to a soldered perfboard with screw-terminal
  blocks as the wire connection points — far more robust for a night outdoors.

## Software stack

- **GPIO:** `gpiozero` (default `lgpio` backend on current Raspberry Pi OS).
- **Brain:** `anthropic` SDK. Model `claude-haiku-4-5-20251001` (fast/cheap Haiku tier — confirm
  the current string when wiring). Reads `ANTHROPIC_API_KEY` from the environment.
- **Audio:** `sounddevice`, `numpy`, `soundfile`; playback via `ffplay`.
- **TTS:** `espeak-ng` now (robotic stand-in, working). **Piper** planned — free, local, far less
  robotic. ElevenLabs later if she wants to be more theatrical.
- **STT:** open decision — a cloud endpoint (fast, needs WiFi) or `faster-whisper` (offline, slower).

**Install gotchas learned (so they don't bite again):**
- `pigpio` is gone from the newest OS repos — don't use it; `Servo.detach()` removes the need.
- `python3-sounddevice` isn't in apt → `pip install --break-system-packages sounddevice`, plus
  `libportaudio2` from apt.
- `apt install` is all-or-nothing — one unfindable name aborts the whole line.
- `aplay` is flaky on this OS/PipeWire → play via `ffplay`.

## Build layers — status & next steps

1. **Mouth moves to sound** — ✅ done. Jaw flaps to audio loudness (our own build of the ChatterPi idea).
2. **Speaks fresh lines** — ◑ half. Voice works (espeak-ng); the Claude brain that generates lines is **next up**.
3. **Listens** — ◔ stubbed. A volume threshold stands in for real speech-to-text.

**Phased plan from here:**
1. **Phase 1 — The brain (next).** Wire the Claude API + the in-character, child-safe system prompt;
   replies as JSON with `visual_cue`; swap the fixed line for a generated fortune; jaw keeps flapping.
2. **Phase 2 — Real ears.** Replace the volume trigger with speech-to-text (settle cloud vs faster-whisper).
3. **Phase 3 — Better voice (optional, anytime).** espeak-ng → Piper.
4. **Phase 4 — Costume vision (camera-gated).** When Module 3 arrives: test it, then fold a photo into
   the same Claude call.
5. **Phase 5 — Into the body (needs the skeleton).** LEDs in sockets, servo linked to the real jaw,
   parts placed, perfboard upgrade.
6. **Phase 6 — Porch hardening (nearer October).** Real distance + noise, lighting, outdoor power, dress rehearsal.

Deadline is Halloween — sessions, not a sprint. Immediate move: **Phase 1**.

## Files in the project

- `BUILD.md` — this plan.
- `SHOPPING_LIST.md` — parts, buy-now vs deferred, with status.
- `purrserpina_buildlog_sensor_and_eyes.md` — session 1 log (speaker, mic, PIR, eyes).
- `purrserpina_buildlog_servo_and_voice.md` — session 2 log (servo, voice, the full loop).
- Scripts on the Pi: `talk_test.py` (full loop), `color_test.py`, `servo_test.py`, `purrserpina_test.py`.
- `purrserpina.py` + `purrserpina_system_prompt.md` — the skeleton of the real pipeline (in the original chat).
