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
PIR motion / summon bell ──► local person-detector gate (MobileNet-SSD, ~300 ms)
        │                            │
        ▼                            ▼
   eyes: purple wake          greeting (pre-rendered, instant)
                                     │
                    ┌────────────────┴────────────────┐
                    │   × 3 questions (enforced in    │
                    │        code, not prompt)        │
                    ▼                                 │
   eyes pulse green — record until silence            │
                    ▼                                 │
   faster-whisper (tiny.en, offline) ── transcript    │
                    ▼                                 │
   Claude Haiku — in-character, child-safe reply      │
                    ▼                                 │
   Piper TTS, synthesized SENTENCE BY SENTENCE ───────┘
   (stall line + "channeling" SFX + eye-storm mask the latency;
    jaw servo flaps to the audio as each sentence plays)
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
prevents them.

**Cheap local models guard the door; the LLM keeps the only job that needs a mind.**
The PIR trips on wind and cats. Rather than paying an API round-trip (~1–2 s) to check every
trigger, a quantized MobileNet-SSD person detector runs on-device in a few hundred
milliseconds, offline and free. It **fails open**: if the gate errs, she greets anyway — a
false greeting to an empty porch is atmosphere; snubbing a real kid is a broken prop. A
motion-persistence fallback (dwell-based, wind-resistant) catches body-hiding costumes like
inflatable dinosaurs that fool the detector.

**Child-safe by design.** Her system prompt is built around one override: mock the
*costume*, never the child — and if a child sounds frightened, the disdain drops instantly.
She gives no real-world advice, asks for no personal information, and each visitor gets a
fresh conversation; no memory bleeds between kids.

**Stateless API, stateful audience.** Conversation memory is a running `messages` list,
resent each turn and wiped on re-arm. Three questions bounds cost, queue length, and
safety surface — and an oracle with ancient laws is *more* in character, not less.

## Hardware

| Part | Role |
| --- | --- |
| Raspberry Pi 4 | runs everything: wake logic, Whisper STT, Piper TTS, servo control |
| HC-SR501 PIR | motion wake (one of three wake sources) |
| Pi Camera Module 3 Wide | person-detection gate; costume critique (multimodal, in progress) |
| 2× RGB LEDs (shared pins) | her eyes — a five-state machine: purple wake → green listen → red think → blue-white speak → dark sleep |
| MG90S servo | the jaw, on hardware PWM (GPIO 18), powered from its own 6 V pack with common ground |
| Fyvadio USB omni mic | ears — 48 kHz capture, downsampled 3:1 to Whisper's 16 kHz |
| SIMOLIO powered speaker | voice, via the 3.5 mm jack |
| Brass Victorian service bell | the summon button — a tactile switch hidden under the plunger |

No lip-sync: the jaw simply flaps while audio plays, which reads as speech with zero
phoneme analysis. Listening is push-to-talk by turn-taking — she only records after
inviting you to speak, so her own voice never feeds back into the mic.

## Software stack

- **Brain:** Claude Haiku via the `anthropic` SDK — fast, cheap, and good enough to be
  witheringly aristocratic. Multimodal (costume critique from a camera frame) rides the
  same call.
- **Ears:** `faster-whisper` (`tiny.en`, int8, CPU) — fully offline after one model
  download. VAD filtering stops tiny-Whisper hallucinating phrases from silence.
- **Voice:** Piper (`en_US-kristin-medium`), tuned via `SynthesisConfig` for an unhurried
  aristocratic drawl.
- **Vision gate:** MobileNet-SSD (COCO) on LiteRT (`ai-edge-litert` — the successor to the
  abandoned `tflite-runtime`).
- **GPIO:** `gpiozero`; audio I/O via `sounddevice` + `ffplay`.

## Repository layout

```
purrserpina_brain.py      the animatronic — single entry point
prompts/system_prompt.md  her character, versioned separately from code
tests/                    one bench script per subsystem (eyes, servo, mic,
                          camera, gate, wake arbitration, voice lab)
docs/buildlogs/           the full build story, session by session
assets/                   sounds, models, voices — gitignored, see below
```

## Running her

```bash
git clone https://github.com/YOURUSERNAME/purrserpina.git && cd purrserpina
sudo apt install python3-numpy libportaudio2 ffmpeg python3-picamera2
pip install --break-system-packages anthropic faster-whisper piper-tts \
    sounddevice ai-edge-litert
export ANTHROPIC_API_KEY=...   # or a systemd EnvironmentFile in production
python3 purrserpina_brain.py
```

`assets/` is not in the repo (large, re-downloadable). Populate it:

| Path | Source |
| --- | --- |
| `assets/voices/en_US-kristin-medium.onnx` + `.onnx.json` | HuggingFace `rhasspy/piper-voices` |
| `assets/models/detect.tflite` + `labelmap.txt` | `coco_ssd_mobilenet_v1_1.0_quant` (TF example models) |
| `assets/sounds/consulting.wav`, `miracle.mp3` | any ambience/SFX you like (e.g. freesound.org) |

The Whisper model self-downloads on first run.

## Status

Fully conversational, mounted in a skull: wake → greeting → three rounds of
listen/think/answer → dismissal → re-arm. In progress: folding the costume critique into
the multimodal call, migrating her into a proper cat-skeleton body, and porch-hardening
for the one night a year she deigns to appear.

*Deadline: Halloween. Obviously.*
