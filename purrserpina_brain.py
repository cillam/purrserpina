#!/usr/bin/env python3
"""
Purrserpina — the BRAIN, on the listening-cues body.

Three things can wake her (see wait_for_wake):
  - gate     — PIR fires AND the local camera gate sees a person
  - persist  — gate says no, but motion is SUSTAINED (the T-rex-suit fallback)
  - button   — the summon bell; a press IS a person, so no gate check
The button is ignored while she's awake or cooling down. Fail-open is the law:
any gate error or missing camera/model means she greets anyway.

Once awake she greets the guest (opener chosen by wake_reason) and names her
terms (three questions); she listens (eyes pulsing green), thinks (red), and
answers in character in her own Piper voice (blue-white), jaw moving in time —
remembering the conversation as it goes. After three questions she dismisses the
guest and sleeps, then re-arms for the next mortal with a blank memory.

The three-question cap is enforced in CODE, not by the model: on the final
question we tell her (via a stage direction) to dismiss the guest. She owns the
flavour of the goodbye; the code owns the fact of it.

Needs:  pip install --break-system-packages anthropic ai-edge-litert
        python3-picamera2 + python3-pil (apt — NOT pip, for picamera2)
        ANTHROPIC_API_KEY in the environment (already set).
        prompts/system_prompt.md   — her character (edit that file to tune her)
        assets/voices|sounds|models/ — kristin .onnx(.json), consulting.wav,
                                     miracle.mp3, detect.tflite + labelmap.txt
                                     (gitignored; see README)

Run:  python3 purrserpina_brain.py     (Ctrl+C to stop)
"""

import os
import random
import re
import subprocess
import wave
from pathlib import Path
import numpy as np
import sounddevice as sd
from queue import Queue
from threading import Thread, Event, Lock
from time import sleep, perf_counter, monotonic
from gpiozero import MotionSensor, RGBLED, Servo, Button
from faster_whisper import WhisperModel
from piper import PiperVoice, SynthesisConfig
from anthropic import Anthropic

# Camera + local person-detector. Imported defensively: if either is missing,
# the gate disables itself and she falls back to waking on PIR alone (fail-open).
try:
    from picamera2 import Picamera2
except ImportError:
    Picamera2 = None
try:
    from PIL import Image
except ImportError:
    Image = None
try:                                    # tflite-runtime is dead; LiteRT is the successor
    from ai_edge_litert.interpreter import Interpreter
except ImportError:
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        Interpreter = None

# ----------------------------------------------------------------------
# Project layout — every path is anchored to the repo, wherever it's cloned.
# assets/ is gitignored (large, re-downloadable); see README for what goes where.
# ----------------------------------------------------------------------
ROOT    = Path(__file__).resolve().parent
ASSETS  = ROOT / "assets"
PROMPTS = ROOT / "prompts"

# ----------------------------------------------------------------------
# Hardware
# ----------------------------------------------------------------------
pir    = MotionSensor(23)
eyes   = RGBLED(red=17, green=27, blue=22)
jaw    = Servo(18)
jaw.detach()
button = Button(24, bounce_time=0.1)    # summon bell (pins 18 + 20); a ring is a mechanical shock

# ----------------------------------------------------------------------
# Wake arbitration — three sources, one guard (ported from tests/wake_test.py)
# ----------------------------------------------------------------------
GATE_MODE         = "local"  # "local" = real camera gate | "off" = PIR alone (always yes)
                             # "stub_yes" / "stub_no" = force the gate's answer (protocol testing;
                             # stub_no is how you exercise the persistence path)
CONFIDENCE        = 0.50     # person score >= this counts as "someone there" — the tuning dial
GATE_MIN_INTERVAL = 3.0      # seconds between gate checks while motion persists (windy nights)
SNAP_SIZE         = (1280, 720)  # what the gate scores were tuned at; also the costume-photo size

PERSIST_WINDOW    = 12.0     # look-back window (s)
PERSIST_DWELL     = 5.0      # cumulative PIR-high seconds required inside the window
PERSIST_EVENTS    = 3        # distinct motion events required inside the window
PERSIST_BACKOFF_START = 60.0   # first unanswered persistence wake rests that path this long (s)
PERSIST_BACKOFF_MAX   = 240.0  # each CONSECUTIVE unanswered one doubles it, up to this cap:
                               # 60 -> 120 -> 240 -> 240... Anyone answering her resets it.
# Keep the HC-SR501 hold-time dial near MINIMUM or it inflates dwell.

MODELS     = ASSETS / "models"
MODEL_FILE = MODELS / "detect.tflite"
LABEL_FILE = MODELS / "labelmap.txt"

# eye-state colors (R, G, B), 0.0-1.0
WAKE_COLOR     = (0.4, 0.0, 0.5)        # purple     — stirring / greeting
LISTEN_COLOR   = (0.0, 1.0, 0.0)        # green      — your turn (pulses)
THINK_COLOR    = (1.0, 0.0, 0.0)        # red        — consulting the beyond
SPEAK_COLOR    = (0.6, 0.8, 1.0)        # blue-white — answering

# ----------------------------------------------------------------------
# Listening config (stop-on-silence)
# ----------------------------------------------------------------------
MIC_RATE          = 48000
BLOCK_SEC         = 0.1
SILENCE_THRESHOLD = 0.02
SILENCE_HANG      = 1.3     # pause she tolerates before deciding you're DONE (was 0.5 — cut you off)
MAX_SECONDS       = 10      # hard cap on a single answer's SPEAKING length (not the begin-wait)
FIRST_START_WAIT  = 7       # after the greeting: how long to wait for you to BEGIN (cold start)
NEXT_START_WAIT   = 6       # later questions: a touch shorter than the first, but still patient
                            # enough that thinking up your next question isn't read as "left"

MOUTH_OPEN, MOUTH_SHUT, FLAP = 0.4, -0.2, 0.13

# Amplitude-driven jaw: mouth tracks the loudness of the wav, so it falls still
# during her pauses and "..." beats instead of chattering straight through them.
JAW_MODE   = "amplitude"   # "amplitude" = track loudness; "flap" = old fixed chatter (A/B)
JAW_FRAME  = 0.1          # seconds per jaw update (10 Hz — servo can track, syllables show)
JAW_SMOOTH = 0.8           # 0-1 glide toward each target (lower = smoother/lazier jaw)
JAW_FLOOR  = 0.06          # normalized RMS at/below this reads as silence -> mouth shut
JAW_GAMMA  = 0.4           # <1 opens the mouth more readily on quieter speech

SPOKE_THRESHOLD = 0.03   # min sustained loudness for a recording to count as speech

def peak_level(audio):
    """RMS of the whole clip — sustained energy, not a momentary pop."""
    return float(np.sqrt(np.mean(audio ** 2)))

# ----------------------------------------------------------------------
# Voice (Piper)
# ----------------------------------------------------------------------
VOICE = ASSETS / "voices" / "en_US-kristin-medium.onnx"

syn = SynthesisConfig(
    volume=1.0,
    length_scale=1.2,
    noise_scale=0.667,
    noise_w_scale=0.8,
    normalize_audio=True,
)

# ----------------------------------------------------------------------
# Conversation rules
# ----------------------------------------------------------------------
MODEL             = "claude-haiku-4-5"   # fast + cheap; pin to a dated string if you like
MAX_QUESTIONS     = 3       # her ancient law. If you change this, edit TERMS's "three" too.
MAX_CONVO_SECONDS = 240     # backstop only (a full 3-question audience can run ~2 min);
                            # the 3-question + per-turn caps already bound a normal audience
COOLDOWN          = 3       # seconds of no-motion settle before re-arming
REPLY_TOKENS      = 200     # a fortune is 1-3 sentences; keeps her terse and fast

# Spoken on waking — canned (instant). The opener depends on WHAT woke her;
# the terms (her three-question law) are shared, so the rule lives in one place.
OPENERS = {
    "gate":    "Ah. A visitor.",
    "persist": "I sense... something. Show yourself.",
    "button":  "You rang?... How refreshingly presumptuous.",
}
TERMS = ("I am purr sir pin ah, and the dead do not chatter idly. "
         "You may put three questions to me, mortal. Choose them with care. Speak.")

# Spoken when a persistence wake gets no reply — so the windy-night false
# alarm reads as her character, not a glitch.
WIND_LINE = "Hm. Only the wind, then."

# Spoken if a guest drifts off before spending all three questions.
EARLY_DISMISSAL = "Hm. Gone already. The living are so fleeting. Begone, then."

# Spoken if Claude is unreachable (porch wifi hiccup) — she stays in character.
ERROR_LINE = ("The veil thickens... I cannot see you clearly tonight. "
              "Return when the spirits are in a kinder humor.")

# Pre-rendered fillers she purrs INSTANTLY while the real fortune is thought up and
# synthesized in the background — so there's no dead air. In character: she's "consulting."
STALL_LINES = [
    "Mm. Let me peer beyond the veil...",
    "Patience, mortal. The spirits stir...",
    "Hm. The threads of fate are tangled... let me see...",
    "Ah. Allow me to consult the darkness a moment...",
]

# Optional atmosphere: a wav that loops quietly UNDER her while she "consults"
# (i.e. while Claude + synthesis run). Drop your own file at this path; if it's
# missing she simply behaves as before. ffplay also reads mp3/ogg if you prefer.
AMBIENCE_WAV    = ASSETS / "sounds" / "consulting.wav"
AMBIENCE_VOLUME = 35      # 0-100 — kept low so it sits under her voice, not over it

# The "channeling" burst: after the stall, while the fortune finishes synthesizing,
# this effect plays once and her eyes storm with colour. Drop your file here;
# if it's missing she still does a brief eye-storm for CHANNEL_MIN_SEC seconds.
CHANNEL_SFX      = ASSETS / "sounds" / "miracle.mp3"
CHANNEL_VOLUME   = 90      # 0-100 — this one's meant to be heard
CHANNEL_MIN_SEC  = 2.5     # fallback storm length if the sfx file isn't there
FLASH_INTERVAL   = 0.07    # seconds between random eye colours during the storm

# ----------------------------------------------------------------------
# Her character lives in prompts/system_prompt.md — edit THAT file to tune her.
# (Versioned separately from code: `git log prompts/system_prompt.md` is the
# history of her personality.)
# ----------------------------------------------------------------------
SYSTEM_PROMPT = (PROMPTS / "system_prompt.md").read_text().strip()

# ----------------------------------------------------------------------
# Load models once
# ----------------------------------------------------------------------
print("Loading Purrserpina's ears, voice, and mind...")
model  = WhisperModel("tiny.en", device="cpu", compute_type="int8", cpu_threads=4)
voice  = PiperVoice.load(str(VOICE))
claude = Anthropic()   # reads ANTHROPIC_API_KEY from the environment


# ----------------------------------------------------------------------
# The camera — ONE Picamera2 for the whole program (it can't be opened twice).
# The wake gate uses it now; the costume photo will use this same instance.
# Started once and left running so continuous autofocus stays settled and a
# snap is near-instant. If it fails to come up, picam2 stays None and the gate
# fails open (she wakes on PIR alone, exactly as before this merge).
# ----------------------------------------------------------------------
picam2   = None
cam_lock = Lock()              # one capture at a time, whichever thread asks
if Picamera2 is not None:
    try:
        picam2 = Picamera2()
        # "BGR888" is picamera2's name for a numpy array in [R, G, B] order —
        # the naming is backwards, the pixels are RGB. Don't "fix" it.
        picam2.configure(picam2.create_still_configuration(
            main={"size": SNAP_SIZE, "format": "BGR888"}))
        picam2.start()
        picam2.set_controls({"AfMode": 2})       # continuous autofocus
        sleep(2)                                 # settle + first focus
        print("   camera up.")
    except Exception as e:
        print(f"   (CAMERA UNAVAILABLE: {e}) — gate fails open, PIR alone wakes her")
        picam2 = None
else:
    print("   (picamera2 not installed) — gate fails open, PIR alone wakes her")


def capture_frame():
    """One RGB numpy frame from the shared camera. Raises if there's no camera."""
    if picam2 is None:
        raise RuntimeError("no camera")
    with cam_lock:
        return picam2.capture_array()


# ----------------------------------------------------------------------
# The local person-gate (ported from tests/gate_test_local.py)
# ----------------------------------------------------------------------
detector = None
if GATE_MODE == "local":
    try:
        if Interpreter is None or Image is None:
            raise RuntimeError("ai-edge-litert or PIL not installed")
        labels = [l.strip() for l in LABEL_FILE.read_text().splitlines()]
        # The model numbers classes from 0 (0 = person), but this labelmap starts
        # with a '???' placeholder row. Drop it, or "person" lands on index 1 —
        # which the model calls BICYCLE, and the gate scores 0.00 forever.
        if labels and labels[0] == "???":
            labels = labels[1:]
        PERSON_ID = labels.index("person")
        detector = Interpreter(model_path=str(MODEL_FILE), num_threads=4)
        detector.allocate_tensors()
        DET_IN  = detector.get_input_details()
        DET_OUT = detector.get_output_details()
        print("   person-gate up.")
    except Exception as e:
        print(f"   (PERSON-GATE UNAVAILABLE: {e}) — gate fails open, PIR alone wakes her")
        detector = None


def best_person_score() -> float:
    """Snap a frame, run the detector, return the best 'person' confidence."""
    frame = capture_frame()
    img = Image.fromarray(frame).convert("RGB").resize((300, 300))
    tensor = np.expand_dims(np.asarray(img, dtype=np.uint8), axis=0)
    detector.set_tensor(DET_IN[0]["index"], tensor)
    detector.invoke()
    classes = detector.get_tensor(DET_OUT[1]["index"])[0]
    scores  = detector.get_tensor(DET_OUT[2]["index"])[0]
    person_scores = [s for c, s in zip(classes, scores) if int(c) == PERSON_ID]
    return float(max(person_scores, default=0.0))


def person_present() -> bool:
    """Is someone actually there? FAIL-OPEN is the law: the PIR already voted
    yes, so any error, missing camera, or missing model means greet anyway.
    Greeting an empty porch is atmosphere; snubbing a real kid is a broken prop."""
    if GATE_MODE == "stub_yes":
        return True
    if GATE_MODE == "stub_no":
        return False
    if GATE_MODE != "local" or detector is None or picam2 is None:
        return True                              # gate off/unavailable -> PIR alone
    try:
        t0 = perf_counter()
        score = best_person_score()
        seen = score >= CONFIDENCE
        print(f"   gate: {perf_counter() - t0:.2f}s  person score {score:.2f} "
              f"-> {'PERSON' if seen else 'empty'}")
        return seen
    except Exception as e:
        print(f"   (gate error: {e}) -> fail-open, treating as person")
        return True


# ----------------------------------------------------------------------
# Wake state — shared between the main loop and gpiozero's callback thread.
# ----------------------------------------------------------------------
state_lock            = Lock()
awake                 = False   # covers wake decision through the END of re-arm (incl. cooldown)
button_requested      = False   # set by the button callback, consumed by wait_for_wake
motion_events         = []      # PIR-high intervals: [start, end_or_None]
last_gate_check       = 0.0
persist_backoff_until = 0.0
wind_streak           = 0       # consecutive persistence wakes nobody answered


def after_audience(wake_reason, answered):
    """Escalating persistence backoff. A real guest (any source) resets it; an
    unanswered persistence wake was probably the wind, so rest that path —
    briefly the first time, doubling each time in a row, capped. One fluke
    costs ~a minute of blind spot; a gusty night still quiets her down.
    Returns the backoff applied in seconds (0 if none), for the console."""
    global wind_streak, persist_backoff_until
    if answered > 0:
        wind_streak = 0                    # a real visitor — the wind theory is dead
        return 0.0
    if wake_reason != "persist":
        return 0.0                         # silent gate/button wakes don't count either way
    backoff = min(PERSIST_BACKOFF_START * 2 ** wind_streak, PERSIST_BACKOFF_MAX)
    wind_streak += 1
    persist_backoff_until = monotonic() + backoff
    return backoff


def on_motion():
    with state_lock:
        motion_events.append([monotonic(), None])


def on_no_motion():
    with state_lock:
        if motion_events and motion_events[-1][1] is None:
            motion_events[-1][1] = monotonic()


def on_button():
    """Runs on gpiozero's thread — keep it tiny. A press only counts while asleep."""
    global button_requested
    with state_lock:
        if awake:
            print("   button IGNORED (awake / cooling down)")
        else:
            button_requested = True


def consume_button() -> bool:
    """True (once) if the bell was rung while she slept."""
    global button_requested
    with state_lock:
        pressed, button_requested = button_requested, False
    return pressed


def persistence_met() -> bool:
    """Dwell, not triggers: cumulative PIR-high seconds AND distinct events inside
    the look-back window. Deliberately hard to trip — leaves flap in the wind."""
    now = monotonic()
    window_start = now - PERSIST_WINDOW
    dwell, events = 0.0, 0
    with state_lock:
        for start, end in motion_events:
            e = end if end is not None else now          # still-open interval
            s = max(start, window_start)
            if e > s:
                dwell += e - s
                events += 1
    return dwell >= PERSIST_DWELL and events >= PERSIST_EVENTS


def prune_events():
    """Drop intervals that ended before the look-back window (keep the list tiny)."""
    cutoff = monotonic() - PERSIST_WINDOW
    with state_lock:
        motion_events[:] = [ev for ev in motion_events if ev[1] is None or ev[1] > cutoff]


def wait_for_wake() -> str:
    """Block until something wakes her; return the wake_reason.
    Priority while asleep: button > gate > persistence."""
    global last_gate_check
    while True:
        # 1) button — a press IS a person
        if consume_button():
            return "button"

        # 2) PIR-driven paths
        if pir.motion_detected:
            now = monotonic()
            if now - last_gate_check >= GATE_MIN_INTERVAL:
                last_gate_check = now
                seen = person_present()
                # the bell may have rung DURING the gate check — it wins
                if consume_button():
                    return "button"
                if seen:
                    return "gate"

            # gate said no (or is rate-limited): consider persistence
            if monotonic() >= persist_backoff_until and persistence_met():
                return "persist"

        prune_events()
        sleep(0.1)


def rearm():
    """Wait for the porch to clear, settle, then accept the next mortal. The button
    stays ignored until the very end of this, and any stray press is discarded."""
    global awake, button_requested
    pir.wait_for_no_motion()
    sleep(COOLDOWN)
    with state_lock:
        awake = False
        button_requested = False
        # forget finished motion, but keep an interval that's still OPEN —
        # otherwise someone already moving would be invisible to persistence
        motion_events[:] = [ev for ev in motion_events if ev[1] is None]


def record(start_wait):
    """Record until the speaker pauses. `start_wait` = seconds to wait for them to BEGIN.
    Returns 16 kHz mono audio, or None if they never speak.

    Two phases, bounded independently:
      - waiting to begin: up to `start_wait` seconds of quiet, then give up
      - speaking: up to MAX_SECONDS of talking, ending early after SILENCE_HANG of quiet
    """
    block        = int(BLOCK_SEC * MIC_RATE)
    hang_blocks  = int(SILENCE_HANG / BLOCK_SEC)
    speak_blocks = int(MAX_SECONDS / BLOCK_SEC)     # cap on SPEAKING length only
    start_blocks = int(start_wait / BLOCK_SEC)      # cap on the wait to BEGIN

    frames, speaking, silent_run, waited = [], False, 0, 0
    peak = 0.0

    try:
        with sd.InputStream(samplerate=MIC_RATE, channels=1, dtype="float32") as stream:
            while True:
                data, _ = stream.read(block)
                level = float(np.sqrt(np.mean(data ** 2)))
                peak = max(peak, level)
                loud = level >= SILENCE_THRESHOLD

                if speaking:
                    frames.append(data.copy())
                    if loud:
                        silent_run = 0
                    else:
                        silent_run += 1
                        if silent_run >= hang_blocks:   # you've finished
                            break
                    if len(frames) >= speak_blocks:     # safety cap on a single answer
                        break
                else:
                    if loud:
                        speaking = True
                        frames.append(data.copy())
                    else:
                        waited += 1
                        if waited >= start_blocks:      # nobody spoke in time
                            break
    except Exception as e:
        # If the audio device fails to open or read (e.g. contention after playback),
        # we surface it here instead of silently returning empty.
        print(f"   (MIC ERROR: {e})")
        return None

    if not frames:
        print(f"   (no speech began within {start_wait}s; peak level {peak:.3f}, "
              f"threshold {SILENCE_THRESHOLD})")
        return None

    audio = np.concatenate(frames).flatten()
    print(f"   (recorded {len(audio) / MIC_RATE:.1f}s, peak {peak:.3f})")
    trim = len(audio) - (len(audio) % 3)            # 48k -> 16k, clean 3:1
    return audio[:trim].reshape(-1, 3).mean(axis=1).astype(np.float32)


def transcribe(audio16):
    """Turn recorded audio into text. Returns '' for silence."""
    if audio16 is None:
        return ""
    t0 = perf_counter()
    segments, _ = model.transcribe(
        audio16, beam_size=1, language="en", vad_filter=True,
    )
    text = " ".join(seg.text for seg in segments).strip()
    print(f"   transcribe: {perf_counter() - t0:.1f}s")
    return text


def ask_purrserpina(history, child_text, questions_used):
    """Send the running conversation to Claude and get her next line.

    The cap is enforced HERE: on the final question we append a stage direction
    telling her to dismiss the guest. The model never owns the count — only the
    flavour of the goodbye. `history` is mutated in place so she remembers the
    whole audience.
    """
    history.append({"role": "user", "content": child_text})

    remaining = MAX_QUESTIONS - questions_used   # questions left AFTER this one
    if remaining <= 0:
        pacing = ("\n\nSTAGE DIRECTION: This is the visitor's final question — they have no "
                  "more after this. Answer it, then dismiss them with grand finality and send "
                  "them on their way into the night.")
    else:
        pacing = (f"\n\nSTAGE DIRECTION: The visitor has {remaining} question(s) remaining "
                  "after this one. Do not dismiss them yet.")

    t0 = perf_counter()
    try:
        resp = claude.messages.create(
            model=MODEL,
            max_tokens=REPLY_TOKENS,
            system=SYSTEM_PROMPT + pacing,
            messages=history,
        )
        reply = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        print(f"   (Claude error: {e})")
        reply = ERROR_LINE
    print(f"   think: {perf_counter() - t0:.1f}s")

    reply = clean_for_speech(reply)             # strip any *asterisks* / markdown before she speaks
    if not reply:
        reply = ERROR_LINE
    history.append({"role": "assistant", "content": reply})
    return reply


def synth(text, path, announce=True):
    """Render Piper speech for `text` into the wav at `path`."""
    t0 = perf_counter()
    with wave.open(path, "wb") as wav:
        voice.synthesize_wav(text, wav, syn_config=syn)
    if announce:
        print(f"   synthesize: {perf_counter() - t0:.1f}s")


def jaw_envelope(path):
    """Read a wav and return (frame_sec, [jaw positions]) tracking its loudness.
    Normalizes to the 90th-percentile SPEECH level — not the single loudest
    sample — so one plosive can't set the ceiling and squash all the ordinary
    speech into a low-amplitude shake. (No moving-average: it ate the short
    bursts canned lines are made of — see log 07. JAW_FRAME already smooths.)"""
    with wave.open(path, "rb") as w:
        rate = w.getframerate(); n = w.getnframes(); ch = w.getnchannels()
        raw = w.readframes(n)
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    if ch > 1:
        samples = samples.reshape(-1, ch).mean(axis=1)
    if samples.size == 0:
        return JAW_FRAME, []
    samples /= 32768.0
    step = max(1, int(JAW_FRAME * rate))
    rms = np.array([np.sqrt(np.mean(samples[i:i + step] ** 2)) if samples[i:i + step].size
                    else 0.0 for i in range(0, len(samples), step)])
    speech = rms[rms > JAW_FLOOR]
    if speech.size == 0:                             # dead-silent clip -> mouth shut
        return JAW_FRAME, [MOUTH_SHUT] * len(rms)
    ref = np.percentile(speech, 90)                  # loud-speech level, ignores lone transients
    denom = max(ref - JAW_FLOOR, 1e-3)
    env = np.clip((rms - JAW_FLOOR) / denom, 0.0, 1.0) ** JAW_GAMMA
    positions = MOUTH_SHUT + env * (MOUTH_OPEN - MOUTH_SHUT)
    return JAW_FRAME, positions.tolist()


def _play_flap(path, final):
    """The original fixed-timer flap — kept for A/B against the amplitude jaw."""
    player = subprocess.Popen(["ffplay", "-autoexit", "-nodisp",
                               "-loglevel", "quiet", path])
    while player.poll() is None:
        jaw.value = MOUTH_OPEN; sleep(FLAP)
        jaw.value = MOUTH_SHUT; sleep(FLAP)
    if final:
        jaw.value = MOUTH_SHUT; sleep(0.3); jaw.detach()


def play(path, final=True):
    """Play a wav while moving the jaw to it (skips gracefully if it's missing).
    `final=False` leaves the jaw engaged, for streaming consecutive sentences.
    The jaw is driven by the wav's own loudness envelope, kept in sync by
    wall-clock position (not loop count), so it never drifts from the audio."""
    if not path or not os.path.exists(path):
        return
    if JAW_MODE != "amplitude":
        return _play_flap(path, final)

    frame_sec, positions = jaw_envelope(path)
    player = subprocess.Popen(["ffplay", "-autoexit", "-nodisp",
                               "-loglevel", "quiet", path])
    pos = MOUTH_SHUT
    t0 = perf_counter()
    while player.poll() is None:
        idx = int((perf_counter() - t0) / frame_sec)       # where we are in the clip
        target = positions[idx] if idx < len(positions) else MOUTH_SHUT
        pos += (target - pos) * JAW_SMOOTH                  # glide, don't snap
        jaw.value = pos
        sleep(frame_sec)
    if final:
        jaw.value = MOUTH_SHUT; sleep(0.3); jaw.detach()


def split_sentences(text):
    """Break her reply into sentence-sized chunks for streaming synthesis.
    Splits on . ! ? that end a sentence; keeps '...' ellipses intact within one."""
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', text.strip())
    return [p.strip() for p in parts if p.strip()]


def clean_for_speech(text):
    """Strip anything the synthesizer shouldn't read aloud: markdown emphasis,
    *stage directions*, quotes, stray symbols. Keeps the words inside **bold**
    but drops *single-asterisk* spans, which are almost always actions (*purrs*)."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)    # **emphasis** -> keep the word
    text = re.sub(r'\*[^*\n]+\*', ' ', text)         # *stage direction* -> drop entirely
    text = text.replace('*', '')                     # any stray asterisks
    text = re.sub(r'[`_#"]', '', text)               # other markdown / quotes TTS shouldn't read
    return re.sub(r'\s+', ' ', text).strip()


def say(text):
    """Synthesize a line on the spot and speak it (for one-off, unhurried lines)."""
    synth(text, "/tmp/purr.wav")
    play("/tmp/purr.wav")


def start_ambience():
    """Start the consulting-bed looping quietly under her. Returns the process, or None."""
    if not os.path.exists(AMBIENCE_WAV):
        return None
    return subprocess.Popen(["ffplay", "-nodisp", "-loglevel", "quiet",
                             "-loop", "0", "-volume", str(AMBIENCE_VOLUME), str(AMBIENCE_WAV)])


def stop_ambience(proc):
    """Stop the consulting-bed (safe to call with None)."""
    if proc is not None:
        proc.terminate()


def sfx(path, volume=100):
    """Play a sound effect to completion WITHOUT moving the jaw (blocks until done)."""
    if not os.path.exists(path):
        return
    subprocess.run(["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet",
                    "-volume", str(volume), str(path)])


def eye_storm(stop_event):
    """Flash the eyes through random colours until `stop_event` is set."""
    while not stop_event.is_set():
        eyes.color = (random.random(), random.random(), random.random())
        sleep(FLASH_INTERVAL)


def channel():
    """The post-stall 'channeling' beat: eyes storm while the effect plays.
    Lasts as long as the sfx (or CHANNEL_MIN_SEC if the file's missing)."""
    flash_stop = Event()
    flash = Thread(target=eye_storm, args=(flash_stop,), daemon=True)
    flash.start()
    if os.path.exists(CHANNEL_SFX):
        sfx(CHANNEL_SFX, CHANNEL_VOLUME)        # plays the effect to completion
    else:
        sleep(CHANNEL_MIN_SEC)                  # no file yet — still give a brief storm
    flash_stop.set()
    flash.join()


def hold_audience(wake_reason):
    """One full visitor: greet, grant up to MAX_QUESTIONS, dismiss. Fresh memory each time.
    Returns how many questions were asked (0 = nobody answered the greeting)."""
    history = []                 # wiped per visitor — never bleed one kid into the next
    questions_used = 0
    convo_start = perf_counter()

    eyes.color = WAKE_COLOR                     # purple — she stirs
    print(f"She wakes ({wake_reason}) and names her terms.")
    play(GREETING_WAVS[wake_reason])

    while questions_used < MAX_QUESTIONS:
        if perf_counter() - convo_start > MAX_CONVO_SECONDS:
            print("   (hard ceiling reached)")
            break

        # green pulse = "your turn, I'm listening" (background thread)
        eyes.pulse(on_color=LISTEN_COLOR, off_color=(0, 0, 0),
                   fade_in_time=0.6, fade_out_time=0.6)
        # first question after the greeting gets a more patient begin-wait
        start_wait = FIRST_START_WAIT if questions_used == 0 else NEXT_START_WAIT
        print(f"   Your turn ({MAX_QUESTIONS - questions_used} left)... speak.")
        audio16 = record(start_wait)

        # Fast silence gate — no transcription needed, just energy.
        if audio16 is None or peak_level(audio16) < SPOKE_THRESHOLD:
            eyes.off()
            print("   (silence)")
            break

        questions_used += 1
        eyes.off()                              # kill the pulse thread...
        eyes.color = THINK_COLOR                # ...red holds, INSTANTLY after they stop

        # Backend thread: transcribe -> Claude -> synth, sentence by sentence.
        segq = Queue()
        def brain_then_synth(audio=audio16, qnum=questions_used):
            try:
                try:
                    heard = transcribe(audio)
                    if not heard:
                        heard = "(the visitor's words were too muddled to make out — " \
                                "ask them, in character, to speak up and repeat)"
                    print(f"   Q{qnum}: {heard!r}")
                    reply = ask_purrserpina(history, heard, qnum)
                except Exception as e:
                    print(f"   (brain error: {e})")
                    reply = ERROR_LINE
                print(f"   (reply ready): {reply!r}")
                for i, sentence in enumerate(split_sentences(reply)):
                    p = f"/tmp/purr_seg_{i}.wav"
                    try:
                        synth(sentence, p, announce=False)
                    except Exception as e:
                        print(f"   (synth error: {e})")
                        continue
                    segq.put(p)
            finally:
                segq.put(None)
        worker = Thread(target=brain_then_synth, daemon=True)
        worker.start()

        # FRONT OF HOUSE, meanwhile: stall line (covers transcribe + Claude),
        # then the channeling storm (covers first-sentence synth).
        amb = start_ambience()
        try:
            play(random.choice(STALL_WAVS))
        finally:
            stop_ambience(amb)
        channel()

        eyes.color = SPEAK_COLOR
        while True:
            seg = segq.get()
            if seg is None:
                break
            play(seg, final=False)
        jaw.value = MOUTH_SHUT; sleep(0.3); jaw.detach()
        worker.join()

    # How did the audience end?
    if questions_used == 0:
        if wake_reason == "persist":            # probably the wind — let her say so
            eyes.color = SPEAK_COLOR
            play(WIND_WAV)
        # otherwise nobody spoke — slip back to sleep silently
    elif questions_used < MAX_QUESTIONS:        # ended early (silence / ceiling) — quick send-off
        eyes.color = SPEAK_COLOR
        play(DISMISS_WAV)
    # else: her final answer already dismissed them — nothing to add.
    return questions_used


# ----------------------------------------------------------------------
# Pre-render every canned line once, so they play INSTANTLY. Only the unique
# fortune is synthesized live each turn — and that's hidden behind a stall.
# (Adds a few seconds to startup; it's a one-time cost.)
# ----------------------------------------------------------------------
print("Pre-rendering her canned lines...")
# One wav per wake source: opener + shared terms rendered as ONE line, so there's
# no ffplay gap or jaw seam between them.
GREETING_WAVS = {}
for _reason, _opener in OPENERS.items():
    _p = f"/tmp/purr_greeting_{_reason}.wav"
    synth(f"{_opener} {TERMS}", _p, announce=False)
    GREETING_WAVS[_reason] = _p
DISMISS_WAV  = "/tmp/purr_dismiss.wav";  synth(EARLY_DISMISSAL, DISMISS_WAV, announce=False)
WIND_WAV     = "/tmp/purr_wind.wav";     synth(WIND_LINE, WIND_WAV, announce=False)
STALL_WAVS = []
for _i, _line in enumerate(STALL_LINES):
    _p = f"/tmp/purr_stall_{_i}.wav"
    synth(_line, _p, announce=False)
    STALL_WAVS.append(_p)
print("Ready.\n")

# ----------------------------------------------------------------------
# Main loop — sleep, wake on motion, hold one audience, re-arm for the next.
# ----------------------------------------------------------------------
print("Warming up the PIR — hold still ~30-60s...")
pir.wait_for_no_motion()
pir.when_motion    = on_motion           # wire the callbacks only AFTER warm-up,
pir.when_no_motion = on_no_motion        # so warm-up false triggers aren't logged as dwell
button.when_pressed = on_button

gate_desc = GATE_MODE if (GATE_MODE != "local" or detector is not None) else "local (UNAVAILABLE -> fail-open)"
print(f"Purrserpina sleeps. Wake sources: gate={gate_desc} | persistence | button. "
      "(Ctrl+C to stop)\n")
try:
    while True:
        reason = wait_for_wake()
        with state_lock:                     # the guard goes up the instant she decides to wake;
            awake = True                     # any press that slipped in before this is discarded
            button_requested = False
        print(f"\n*** WAKE (wake_reason = {reason}) ***")

        answered = hold_audience(reason)

        sleep(0.5)
        eyes.off()                              # back to sleep
        print("...she sinks back into the dark.")

        # A persistence wake nobody answered was probably the wind: rest that path,
        # longer each time in a row. A real guest (any source) resets the streak.
        backoff = after_audience(reason, answered)
        if backoff:
            print(f"   persistence path backing off {backoff:.0f}s (wind streak {wind_streak})")

        rearm()
        print("   re-armed, memory blank.\n")
except KeyboardInterrupt:
    print("\nPurrserpina rests.")
finally:
    eyes.off()
    jaw.detach()
    if picam2 is not None:
        try:
            picam2.stop()
            picam2.close()
        except Exception:
            pass
