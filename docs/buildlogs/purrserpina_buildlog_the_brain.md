# Purrserpina — Build Log: The Brain (and her voice's latency)

*Covers everything since the last project summary. This is the session where she stopped echoing and started **thinking** — Phase 1 done — plus the full latency fight and the effects layer. The camera arrived at the very end (hardware proven, not yet wired in).*

## Headline
The full **hear → think → speak** loop now runs on the breadboard **with the Claude brain**. Walk up and she wakes, greets you, grants three questions, and answers each one as Her Infernal Majesty Purrserpina — a real, in-character, child-safe fortune — in kristin's voice with the jaw moving in time, then dismisses you and re-arms for the next visitor with a blank memory. The main script is now **`purrserpina_brain.py`** (supersedes the echo test).

## Architecture decided/confirmed this session
- **Multi-turn, not single-shot.** The API is stateless, so "memory" is just a running `messages` list we resend each turn. Each visitor gets a fresh list; it's wiped on re-arm so visitor #2 never inherits #1's conversation.
- **Bounded audience = in character.** She grants **three questions**, announced in the greeting as ancient law, then dismisses. An oracle with a question budget is *more* Purrserpina, not less — and it self-limits queue length and child-safety surface.
- **The cap is enforced in CODE, never by the prompt.** The model miscounts and folds to "pleeease one more." So code owns the *fact* of the limit; on the final question we inject a stage-direction telling her to dismiss, and the prompt only owns the *flavour* of the goodbye.
- **Replies are plain prose** (JSON `visual_cue` still deferred until a screen exists) — simpler, and it set up sentence-streaming.
- **Costume vision** stays the planned one-call multimodal design; camera just arrived (see Next Steps).

## What `purrserpina_brain.py` does now
One visitor = `hold_audience()`:
1. **Wake** (purple) → speaks the pre-rendered **greeting** that names the three-question rule.
2. For up to three questions: **green-pulse listen** → **red think** → instant **stall line** → **channeling burst** (effect + eye-storm) → **blue-white streamed answer** (jaw in time).
3. **Dismiss** (her own final answer dismisses after Q3; a canned line covers early exits) → **sleep** → `wait_for_no_motion()` + cooldown → re-arm with empty memory.

Built onto the **listening-cues** base, preserved intact: `tiny.en` / `beam_size=1`, the locked kristin `SynthesisConfig` (volume 1.0, length_scale 1.2, noise_scale 0.667, noise_w_scale 0.8), the `record()`/`transcribe()` split, and timing prints.

## The latency fight (this took the most iterations)
The Pi-local synthesis was always the bottleneck, exactly as predicted. The fix came in layers:
- **Stall line + pre-rendering.** `say()` split into `synth()` (render to wav) + `play()` (play + flap jaw). Every *canned* line (greeting, dismissals, stalls) is pre-rendered once at startup so it fires instantly. The real fortune runs on a **background thread** while an instant stall plays over the top.
- **Why the stall wasn't enough:** Piper's medium voice renders at ~**real-time**, so a 3-sentence fortune takes ~7s to synthesize and **outran** the ~2s stall → dead air spilled out past it. (The console's `synthesize:` print confirmed it.)
- **Sentence-streaming — the actual fix.** The reply is now synthesized **one sentence at a time** via a producer/consumer `Queue`: playback starts the instant sentence 1 is ready (the stall covers exactly that), and sentences 2+ synthesize *while* earlier ones play. `play(..., final=False)` keeps the jaw engaged across sentences. `split_sentences()` chunks on `.!?` but keeps her "..." ellipses intact.
- **Ambience bed (optional).** `AMBIENCE_WAV` loops quietly under the stall and through any residual gap, clearing as her voice begins — also covers the slow-Claude seam. Low volume (35).
- **Channeling burst.** After the stall, while the fortune finishes rendering, `channel()` plays a sound effect (`CHANNEL_SFX`, e.g. freesound 455367) at volume 90 while `eye_storm()` flashes random colours, then settles to blue-white for the pronouncement. `sfx()` plays effects **without** moving the jaw (it's not her talking).

## Gotchas that bit us (the valuable part)
- **API key safety.** Key lives in its own dotfile `~/.purrserpina.env` (`chmod 600`), sourced from `~/.bashrc` — *not* in the project dir, so it never rides along in scp/pastes/logs/git. Typed on the Pi over SSH so it's never in shell history. (When she auto-starts as a systemd service later, `~/.bashrc` won't load — switch to a systemd `EnvironmentFile=` then. Also worth: rotate if it ever leaks, and set a spend limit since she'll run unattended.)
- **`record()` was conflating two timers.** The old loop made `MAX_SECONDS` bound the begin-wait *and* the speaking, so a long first-wait ate speaking time. Rewrote it into two independently-bounded phases: **wait-to-begin** vs **max-talking-length**.
- **`SILENCE_HANG` 0.5s was too short** — a mid-question breath ended the turn. Now **1.3s**. Begin-wait split into **`FIRST_START_WAIT` 7s** (cold, after the greeting) vs **`NEXT_START_WAIT` 6s** (later — but still patient enough that *thinking up* the next question isn't read as leaving).
- **The "drops out before Q3" bug — two causes.** First the **90s wall-clock ceiling** was simply too tight: a real 3-question audience with full answers runs ~2 min, and the ceiling check at the top of the loop killed Q3. Raised to **240s** (it's redundant anyway — the 3-question + per-turn caps already bound the audience). When it persisted, we **instrumented `record()`** instead of guessing: it now catches mic/device errors and prints the **peak input level** on an empty capture, distinguishing "mic dead" vs "too quiet" vs "captured but no words." That surfaced the real cause and it now works.
- **Asterisks reaching the voice.** Haiku slipped in `*stage directions*` / `**emphasis**` despite the prompt. Fix is **code, not prompt**: `clean_for_speech()` keeps the words inside `**bold**`, drops `*single-asterisk*` spans (almost always actions like `*purrs*`), and scrubs stray symbols — applied before synthesis. Prompt also reframed around "you have no body here, only a voice."
- **Red eyes weren't holding during "think."** Setting `eyes.color` does **not** stop a running gpiozero **pulse thread**, so the green listen-pulse kept overwriting the red. Fix: explicit `eyes.off()` before `eyes.color = THINK_COLOR`. (Other colours worked because no pulse was running when they were set.) If the brief flicker annoys, the cleaner path is a **steady** green listen instead of a pulse — kills the whole class of bug.
- **mDNS:** scp needs **`purrserpina.local`**, not `purrserpina` (and same network, no VPN). `hostname -I` on the Pi gives the raw IP as a fallback.
- **Camera tooling:** newest Pi OS uses **`rpicam-*`** (not `libcamera-*`); Module 3 sensor is **IMX708**; Python lib is **picamera2** (not the old `picamera`); CSI ribbon is **not hot-pluggable** (power off to seat it).

## Key constants (top of `purrserpina_brain.py`)
- Brain: `MODEL = claude-haiku-4-5`, `MAX_QUESTIONS = 3`, `MAX_CONVO_SECONDS = 240`, `COOLDOWN = 3`, `REPLY_TOKENS = 200`.
- Ears: `SILENCE_HANG = 1.3`, `MAX_SECONDS = 10`, `FIRST_START_WAIT = 7`, `NEXT_START_WAIT = 6`.
- Effects: `AMBIENCE_WAV` @ vol 35; `CHANNEL_SFX` @ vol 90; `CHANNEL_MIN_SEC = 2.5`; `FLASH_INTERVAL = 0.07`.
- Eyes: WAKE purple `(0.4,0,0.5)` · LISTEN green `(0,1,0)` pulse · THINK red `(1,0,0)` · SPEAK blue-white `(0.6,0.8,1.0)`.
- Sound files live in `~/purr-sounds/`. New pip dep: `anthropic` (`pip install --break-system-packages anthropic`).

## Current state — what works
Full conversational animatronic on the breadboard, **camera excepted**: motion wake → greeting → three rounds of (listen → think → stall → channel → streamed answer) → dismiss → sleep → re-arm fresh. In-character, child-safe Haiku fortunes; asterisks scrubbed; latency masked so there's no dead air; eye-state machine correct (red now holds while thinking). Camera **hardware proven** (`rpicam-still` produced a clean photo) but not yet captured from Python or wired into the brain.

## Open issues & next steps
1. **Camera software (next):** confirm **picamera2** captures from Python (`python3 -c "from picamera2 import Picamera2"`), then a small `camera_test.py` to prove resolution/autofocus on the IMX708 in isolation — no brain changes.
2. **Costume-critique integration:** fold a captured JPEG into `ask_purrserpina` as a base64 image block in the **same** multimodal Claude call as the dialogue. Decide **when** to snap (wake? first question?), make the system prompt vision-aware, and lean hard on the existing **"critique the costume, never the kid"** guardrail now that vision is real.
3. **Remaining seams (polish):** between-sentence `ffplay` gaps (go to continuous PCM if choppy); the pulse→red flicker (switch to steady green if it bugs); reap the ambience `ffplay` (currently `terminate()` without `wait()`); a long `CHANNEL_SFX` adds fixed per-turn delay — keep it ~2–3s.
4. **Workflow:** consider live SSH editing (VS Code Remote-SSH) so prompt/constant tuning is save-and-run instead of scp each time; and a git repo on the Pi so prompt edits are versioned/revertible.
5. **Into the body + porch hardening (unchanged):** mount LEDs/servo/mic/speaker/camera, perfboard with screw terminals, lighting for the camera, outdoor power/weather, re-trigger gating with the camera's help, dress rehearsal.

## Scripts
- **`purrserpina_brain.py`** — the main script now: the full conversational animatronic minus camera.
- `ears_test_piper.py` — earlier echo-only test, kept as a fallback.
- Config: `~/.purrserpina.env` (the API key, sourced from `~/.bashrc`).

*Deadline: Halloween. Still prototype-first, still built in focused testable rungs. Brain done; eyes (the seeing kind) next.*
