# Purrserpina — Build Log: Speech-to-Text, Voice & Listening Cues

*Continues from `purrserpina_buildlog_servo_and_voice.md`, which ended with the full
motion → listen → speak → jaw loop working and the voice as the next job. This session
gave her real ears (offline speech-to-text), a real voice (Piper), and clear turn-taking cues.*

## What's working now
The full **hear → think → speak** loop runs end to end on the breadboard — everything
except the Claude brain. Walk up and:

- She wakes (purple eyes) and speaks a greeting: *"Speak, and I shall listen."*
- Her eyes **pulse green** — the guest's cue to talk.
- She records until you stop talking (stop-on-silence) and transcribes your words offline.
- Eyes go **red** while she thinks, then **blue-white** as she answers.
- She **echoes your words back** in her own voice (kristin), jaw moving in time.

She repeats rather than generates — swapping that echo for a Claude fortune is the only
thing left to make her conversational.

## Ears — offline speech-to-text (faster-whisper)
- Engine: faster-whisper, CPU, int8. `pip install --break-system-packages faster-whisper`.
- Model: `tiny.en` for speed (`base.en` is more accurate but noticeably slower — a one-word
  swap). The model auto-downloads once (needs WiFi that once), then runs fully offline.
- Settings: `beam_size=1`, `vad_filter=True` (stops tiny-Whisper hallucinating phantom
  phrases out of silence), `language="en"`, `cpu_threads=4`.
- **Mic-rate fix:** the Fyvadio mic can't capture at 16 kHz (Whisper's rate), only 48 kHz.
  So record at 48 kHz and downsample 3:1 by averaging every 3 samples (the averaging
  doubles as a cheap anti-alias filter — clean because 48000 ÷ 3 = 16000).
- **Stop-on-silence:** instead of a fixed window, record in 100 ms blocks — start when the
  guest speaks, stop after ~0.5 s of quiet. Kills the dead-air wait of a fixed timer.

## Voice — Piper (kristin)
- Engine: Piper (piper1-gpl). `pip install --break-system-packages piper-tts`. Vastly more
  natural than the old espeak stand-in.
- Voice: `en_US-kristin-medium` (.onnx + .onnx.json downloaded from HuggingFace
  `rhasspy/piper-voices` into `~/piper-voices`). Played via ffplay.
- **Programmatic tuning** via `SynthesisConfig` (no JSON editing): `volume`, `length_scale`
  (higher = slower), `noise_scale` (tone variation), `noise_w_scale` (timing variation),
  `normalize_audio`.
- **Locked settings:** volume 1.0, length_scale 1.2 (gently slowed for an unhurried draw),
  noise_scale 0.667, noise_w_scale 0.8 (kristin's defaults), no effects.
- Built a `voice_test.py` lab (no GPIO) to audition the knobs live before committing.
- **Effects deferred:** Spotify's `pedalboard` (pip-installable, ARM wheels) is the clean way
  to add reverb / pitch-shift later — Piper itself has no pitch control. Noted, not used.

## Listening cues (so the guest knows it's their turn)
The terminal's "Listening..." print is invisible on a porch, so she now signals in-world:

- **Verbal:** she speaks *"Mmm. A visitor. Speak, and I shall listen."* on waking, **before**
  recording — so she never records her own greeting, and a voice telling you to speak is the
  clearest possible turn-signal.
- **Visual eye states:** purple (waking) → **pulsing green** (your turn / listening) → red
  (thinking) → blue-white (answering) → off (asleep). The green *pulses* on a background
  thread, which reads as "actively attending" rather than just "on."
- **Refactor:** the old `listen()` split into `record()` + `transcribe()` so the eyes can
  change state between "hearing you" and "thinking" — also makes wiring in the stall line and
  the Claude call cleaner later, since there are now clean seams between stages.

## Latency (open thread)
There's still a noticeable gap between the guest finishing and Purrserpina answering.
Tuning the ears (tiny + beam 1 + shorter silence) only helped *slightly* — which itself is a
clue that transcription isn't the main cost. Prime suspect: Piper synthesizes the **whole**
line before any sound plays, and the medium voice runs ≈ real-time on a Pi 4. The current
script prints `transcribe:` and `synthesize:` times to pin it down. Likely fix: **Piper
streaming** (start playing as the first chunk is ready) plus a **stall line** (a pre-made
filler she speaks instantly while the real work runs in a background thread).

*Key reassurance: the Claude call will be fast and off-device — the Pi-local work is the real
bottleneck, so adding the brain won't make this dramatically worse.*

## Concepts learned
- Claude's API takes **text and images, not audio**, so speech-to-text is a mandatory
  separate step. Voice in the chat app transcribes first too; we're just building that step.
- The cloud Claude call is fast; the slow part is the **Pi running Whisper locally**.
- **VAD filtering** is the fix for Whisper inventing phantom "Thank you."-type phrases from
  silence or noise.
- Piper's character knobs: `length_scale` = speed (inverse — bigger is slower), `noise_scale`
  = tone wobble, `noise_w_scale` = timing wobble, `volume` = flat gain (no variation).
  No pitch control — depth is a post-processing effect (ffmpeg `-af` or pedalboard).
- A **listening cue is essential**: the guest needs to know when to talk (verbal invite +
  pulsing-green eyes), and the pause needs to read as *working*, not *broken*.

## Deployment note captured for later (re-trigger gating)
Once she's on the porch she must greet each visitor **only once**. The guest stands there
moving, so the PIR keeps firing and she'd re-greet every few seconds. Fix: after an exchange,
`wait_for_no_motion()` + a short cooldown before re-arming, so she only re-greets when the
porch clears and someone new approaches. The HC-SR501's own output-timeout dial means
"no motion" isn't instant — tune together. The camera will do this smarter later (actually
seeing a new person). Deliberately left out of the test scripts so they re-trigger instantly
during testing.

## Scripts on the Pi
- `ears_test_piper.py` — current main test: the full loop with listening cues + timing prints.
- `voice_test.py` — interactive voice lab (no GPIO): type lines, tweak Piper knobs live.
- Earlier: `talk_test.py`, `color_test.py`, `servo_test.py`, `purrserpina_test.py`, `ears_test.py`.

## Next steps
1. Read the `transcribe:` / `synthesize:` numbers, then fix the real latency cause (likely
   Piper streaming + a stall line).
2. **Phase 1 — the brain:** Claude API + child-safe, in-character system prompt; swap the echo
   for a generated fortune. Needs the Anthropic API key and a first system-prompt draft.
3. Camera / costume vision when Module 3 arrives.
4. Into the body (mount in the skeleton, perfboard upgrade) + re-trigger gating.
5. Porch hardening.
