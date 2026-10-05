# Purrserpina 🐈‍⬛

**A conversational animatronic fortune-teller, built on a Raspberry Pi 4 and the Claude API.**

Her Infernal Majesty Purrserpina is a long-dead, impossibly snooty aristocrat cat who reads
the fates of trick-or-treaters — currently haunting a humble skull while her proper feline
vessel is prepared. Walk up to her porch and she wakes, grants you exactly three
questions, and answers each one — in character, in her own voice, jaw moving in time with
her words — then dismisses you into the night and forgets you ever existed.

Every fortune is generated live. Nothing is scripted except her manners.

## How she works

```
PIR motion ──► on-device person gate (MobileNet-SSD, ~0.1–0.2 s)
   │              └─ gate says no, but motion is SUSTAINED ──► persistence fallback
summon bell ───────────────────────────────────────────────► wakes her instantly
        │
        ▼
   eyes: purple — greeting chosen by what woke her (pre-rendered, instant)
        │
        ▼
   ┌──── × 3 questions (counted in code, not the prompt) ────┐
   │  eyes pulse green — record until the guest goes quiet    │
   │  faster-whisper (tiny.en, offline) ──► transcript        │
   │  Claude Haiku ──► in-character, child-safe reply         │
   │  Piper TTS, synthesized SENTENCE BY SENTENCE             │
   │  (stall line + "channeling" SFX + eye-storm mask the     │
   │   latency; the jaw tracks the loudness of her voice)     │
   └──────────────────────────────────────────────────────────┘
        │
        ▼
   dismissal ──► dark ──► re-arm with a blank memory
```

The whole exchange runs on a $60 single-board computer plus one API call per question.

## Engineering highlights

**Latency is theater.** A Pi 4 synthesizes Piper speech at roughly real time, so a
three-sentence fortune would mean ~7 s of dead air. The fix is a pipeline: the reply is
split into sentences and synthesized on a producer/consumer queue, playback starting the
instant sentence one is ready — while a pre-rendered stall line ("*Patience, mortal. The
spirits stir...*"), an ambience bed, and a color-storm "channeling" effect turn the
remaining gap into part of the act. The pause reads as consulting the beyond, not buffering.

**The rules live in code, not the prompt.** LLMs miscount and fold to "pleeease one more" —
so the three-question limit is enforced by the loop, which injects a stage direction on the
final turn telling her to deliver a grand dismissal. The model owns the *flavor* of the
goodbye; the code owns the *fact* of it. Same principle everywhere: a `clean_for_speech()`
pass strips any `*stage directions*` the model sneaks in, rather than hoping the prompt
prevents them. When a guest opens with small talk ("trick or treat!") instead of a
question, Haiku may flag it with a tag and ask what creature they've come as — but *code*
decides whether that flag is honored, refunds the question, and caps it at once per visitor.

**Three wake sources, one guard.** The PIR trips on wind and cats, so it never decides
alone. A quantized MobileNet-SSD person detector runs on-device in a fraction of a second —
offline, free, no API round-trip. It **fails open**: if the camera or model errs, she greets
anyway — a false greeting to an empty porch is atmosphere; snubbing a real kid is a broken
prop. A dwell-based persistence fallback catches body-hiding costumes (inflatable dinosaurs,
ghost sheets) that fool the detector; if a persistence wake gets no reply, she remarks
"*Hm. Only the wind, then.*" and rests that path on an escalating backoff (60 s, doubling
to a 4-minute cap, reset the moment anyone actually answers her). And a brass service bell
summons her instantly — ignored while she's mid-audience, because kids *will* mash it.

**The jaw follows the voice.** No lip-sync and no phoneme analysis: each line's loudness
envelope is computed from the wav (normalized to the 90th-percentile speech level, so one
plosive can't flatten everything else) and the servo glides along it, synced by wall-clock
time so it can't drift from the audio. She opens on stressed syllables and falls still on
her "..." pauses.

**Child-safe by design.** Her system prompt is built around one override: mock the
*costume*, never the child — and if a child sounds frightened, the disdain drops instantly.
She gives no real-world advice, asks for no personal information, and each visitor gets a
fresh conversation; no memory bleeds between kids. See [Privacy](#privacy) for what she
keeps (almost nothing) and why she *asks* about costumes rather than looking.

**Stateless API, stateful audience.** Conversation memory is a running `messages` list,
resent each turn and wiped on re-arm. Three questions bounds cost, queue length, and
safety surface — and an oracle with ancient laws is *more* in character, not less.

## Privacy

Purrserpina's guests are mostly children, so she is built to keep as little as possible,
for as short a time as possible. The guiding rule: **nothing about a guest is written to
disk on the Pi, and nothing that could identify a guest leaves the house.**

### What happens to each kind of data

| Data | Where it goes | Kept? |
| --- | --- | --- |
| **Camera frames** | Scored on the Pi by the person detector, in memory | **Never saved, never sent.** Each frame is discarded the moment it's scored; only a number ("person: 0.84") survives, and only in the console. |
| **Guest's voice** | Recorded in memory, transcribed **on the Pi** by Whisper | **Never saved, never sent.** The audio is discarded after transcription; no recording ever leaves the device. |
| **Transcribed words** | Sent to the Claude API as text, with her replies, for that one visitor's conversation | In memory on the Pi until she re-arms, then wiped. On Anthropic's side, see below. |
| **Her replies** | Synthesized to short wav files in `/tmp` | Her own voice only — no guest content. Overwritten every turn. |

### The costume decision: ask, don't look

The original plan sent a photo of each guest's costume to Claude in the same call as their
question, so she could critique what she saw. **We chose not to.** API inputs are retained on
Anthropic's servers for a period after each request (see below), and a photo of a child is a
very different thing to have sitting on a server than the question that child asked.

So she *asks* instead. If a guest opens with small talk, she may ask what creature they've
come as and take their word for it — no image is ever captured for this. The camera's only
job is the on-device "is someone there?" gate, and its frames never leave the Pi.

A future, optional **sight mode** may bring costume vision back for settings where it fits
(an adult party where everyone knows a camera is in use, say). If it's built, it will be
**off by default**, switched on by the host per event — never chosen automatically by
guessing guests' ages from the camera — and documented here before it ships.

### What reaches Anthropic, and for how long

Only the **text** of each conversation (the transcribed questions and her replies) is sent
to the Claude API. API traffic falls under Anthropic's commercial terms: it is **not used to
train models** by default, and inputs and outputs are **automatically deleted within 30
days**, with exceptions — notably, content flagged by automated systems as violating the
Usage Policy can be retained longer, and data may be retained where the law requires it.
The source of truth is Anthropic's privacy center:
[How long do you store my organization's data?](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)

The API account she uses is not enrolled in Anthropic's Development Partner Program. The API key lives only on the Pi, in a `chmod 600` file
outside the repo, and is never committed (`git grep "sk-ant"` is part of the routine).

### Deletion, in practice

- **Per visitor:** the conversation history is wiped when she re-arms; the next guest starts
  blank. Nothing about the previous guest survives on the Pi.
- **Per night:** nothing to delete — guest audio, frames, and transcripts are never written
  to disk in the first place.
- **On Anthropic's side:** conversation text is deleted on their schedule (within 30 days by
  default, per the policy above). There is no per-visitor deletion step to perform.

### Known edges (and what we do about them)

- **Console output.** The script prints each transcribed question to the terminal for
  debugging. Over an SSH session that scrolls away; but under **systemd** (the planned
  porch deployment) stdout goes to the system journal, which persists on disk. Before she
  runs as a service, transcript printing gets disabled or the journal set not to persist —
  otherwise a night's questions would quietly accumulate in a log.
- **Bench tools.** `tests/gate_diag.py` deliberately saves one camera frame to
  `/tmp/gate_frame.jpg` so you can see what the detector sees. It's for tuning on yourself
  — never run it on the porch with guests in frame — and it overwrites the same file each
  run (`rm /tmp/gate_frame.jpg` to clear it).

## Hardware

| Part | Role |
| --- | --- |
| Raspberry Pi 4 | runs everything: wake logic, person detector, Whisper STT, Piper TTS, servo control |
| HC-SR501 PIR | motion — one of three wake sources, never trusted alone |
| Pi Camera Module 3 Wide | on-device person-detection gate only — frames never saved or sent |
| 2× RGB LEDs (shared pins) | her eyes — a five-state machine: purple wake → green listen → red think → blue-white speak → dark sleep |
| MG90S servo | the jaw, on hardware PWM (GPIO 18), powered from its own 6 V pack with common ground |
| Fyvadio USB omni mic | ears — 48 kHz capture, downsampled 3:1 to Whisper's 16 kHz |
| SIMOLIO powered speaker | voice, via the 3.5 mm jack |
| Brass Victorian service bell | the summon button — a tactile switch hidden under the plunger (GPIO 24) |

Listening is push-to-talk by turn-taking — she only records after inviting you to speak, so
her own voice never feeds back into the mic. A stray sound that trips the mic but turns out
too quiet to be speech is discarded, and she keeps listening rather than giving up on you.

## Software stack

- **Brain:** Claude Haiku via the `anthropic` SDK — fast, cheap, and good enough to be
  witheringly aristocratic. Text only, by design (see [Privacy](#privacy)).
- **Ears:** `faster-whisper` (`tiny.en`, int8, CPU) — fully offline after one model
  download. VAD filtering stops tiny-Whisper hallucinating phrases from silence.
- **Voice:** Piper (`en_US-kristin-medium`), tuned via `SynthesisConfig` for an unhurried
  aristocratic drawl.
- **Vision gate:** MobileNet-SSD (COCO) on LiteRT (`ai-edge-litert` — the successor to the
  abandoned `tflite-runtime`), via `picamera2`.
- **GPIO:** `gpiozero`; audio I/O via `sounddevice` + `ffplay`.

## Repository layout

```
purrserpina_brain.py      the animatronic — single entry point
prompts/system_prompt.md  her character, versioned separately from code
tests/                    one bench script per subsystem (eyes, servo, mic,
                          camera, gate, gate diagnostic, wake arbitration, voice lab)
docs/buildlogs/           the full build story, session by session
assets/                   sounds, models, voices — gitignored, see below
```

## Running her

```bash
git clone https://github.com/YOURUSERNAME/purrserpina.git && cd purrserpina
sudo apt install python3-numpy libportaudio2 ffmpeg python3-picamera2 python3-pil
pip install --break-system-packages anthropic faster-whisper piper-tts \
    sounddevice ai-edge-litert
export ANTHROPIC_API_KEY=...   # or a systemd EnvironmentFile in production
python3 purrserpina_brain.py
```

`picamera2` comes from **apt, not pip** — it's built against the OS's exact libcamera stack.
If the camera or detector can't load, she says so at startup and falls back to waking on
motion alone.

`assets/` is not in the repo (large, re-downloadable). Populate it:

| Path | Source |
| --- | --- |
| `assets/voices/en_US-kristin-medium.onnx` + `.onnx.json` | HuggingFace `rhasspy/piper-voices` — both files; Piper silently needs the `.json` |
| `assets/models/detect.tflite` + `labelmap.txt` | `coco_ssd_mobilenet_v1_1.0_quant` (TF example models). The labelmap's first row is a `???` placeholder; the code strips it so "person" maps to class 0. |
| `assets/sounds/consulting.wav`, `miracle.mp3` | any ambience/SFX you like (e.g. freesound.org) |

The Whisper model self-downloads on first run.

## Status

Fully conversational on the bench: three-source wake (camera gate, persistence, summon
bell) → greeting → three rounds of listen/think/answer → dismissal → re-arm. In progress:
the full wake-test protocol, migrating her into a proper cat-skeleton body, and
porch-hardening for the one night a year she deigns to appear. Later, optionally: a
per-event sight mode (see [Privacy](#privacy)).

*Deadline: Halloween. Obviously.*
