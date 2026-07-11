#!/usr/bin/env python3
"""
Purrserpina — the BRAIN, on the listening-cues body.

Motion wakes her; she greets the guest and names her terms (three questions);
she listens (eyes pulsing green), thinks (red), and answers in character in her
own Piper voice (blue-white), jaw moving in time — remembering the conversation
as it goes. After three questions she dismisses the guest and sleeps, then
re-arms for the next mortal with a blank memory.

The three-question cap is enforced in CODE, not by the model: on the final
question we tell her (via a stage direction) to dismiss the guest. She owns the
flavour of the goodbye; the code owns the fact of it.

Still prints transcribe/synthesize times — kept for the latency pass coming next
(stall line + sentence streaming), which is deliberately NOT in here yet.

Needs:  pip install --break-system-packages anthropic
        ANTHROPIC_API_KEY in the environment (already set).
        prompts/system_prompt.md   — her character (edit that file to tune her)
        assets/voices|sounds/      — kristin .onnx(.json), consulting.wav,
                                     miracle.mp3 (gitignored; see README)

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
from threading import Thread, Event
from time import sleep, perf_counter
from gpiozero import MotionSensor, RGBLED, Servo
from faster_whisper import WhisperModel
from piper import PiperVoice, SynthesisConfig
from anthropic import Anthropic

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
pir  = MotionSensor(23)
eyes = RGBLED(red=17, green=27, blue=22)
jaw  = Servo(18)
jaw.detach()

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

MOUTH_OPEN, MOUTH_SHUT, FLAP = 0.3, -0.2, 0.13

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
MAX_QUESTIONS     = 3       # her ancient law. If you change this, edit GREETING's "three" too.
MAX_CONVO_SECONDS = 240     # backstop only (a full 3-question audience can run ~2 min);
                            # the 3-question + per-turn caps already bound a normal audience
COOLDOWN          = 3       # seconds of no-motion settle before re-arming
REPLY_TOKENS      = 200     # a fortune is 1-3 sentences; keeps her terse and fast

# Spoken on waking — canned (instant) and states her terms as lore.
GREETING = ("Ah. A visitor. I am purr sir pin ah, and the dead do not chatter idly. "
            "You may put three questions to me, mortal. Choose them with care. Speak.")

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


def play(path, final=True):
    """Play a wav while flapping the jaw to it (skips gracefully if it's missing).
    `final=False` leaves the jaw engaged, for streaming consecutive sentences."""
    if not path or not os.path.exists(path):
        return
    player = subprocess.Popen(["ffplay", "-autoexit", "-nodisp",
                               "-loglevel", "quiet", path])
    while player.poll() is None:
        jaw.value = MOUTH_OPEN; sleep(FLAP)
        jaw.value = MOUTH_SHUT; sleep(FLAP)
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


def hold_audience():
    """One full visitor: greet, grant up to MAX_QUESTIONS, dismiss. Fresh memory each time."""
    history = []                 # wiped per visitor — never bleed one kid into the next
    questions_used = 0
    convo_start = perf_counter()

    eyes.color = WAKE_COLOR                     # purple — she stirs
    print("She wakes and names her terms.")
    play(GREETING_WAV)

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
        pass                                    # nobody spoke — slip back to sleep silently
    elif questions_used < MAX_QUESTIONS:        # ended early (silence / ceiling) — quick send-off
        eyes.color = SPEAK_COLOR
        play(DISMISS_WAV)
    # else: her final answer already dismissed them — nothing to add.


# ----------------------------------------------------------------------
# Pre-render every canned line once, so they play INSTANTLY. Only the unique
# fortune is synthesized live each turn — and that's hidden behind a stall.
# (Adds a few seconds to startup; it's a one-time cost.)
# ----------------------------------------------------------------------
print("Pre-rendering her canned lines...")
GREETING_WAV = "/tmp/purr_greeting.wav"; synth(GREETING, GREETING_WAV, announce=False)
DISMISS_WAV  = "/tmp/purr_dismiss.wav";  synth(EARLY_DISMISSAL, DISMISS_WAV, announce=False)
STALL_WAVS = []
for _i, _line in enumerate(STALL_LINES):
    _p = f"/tmp/purr_stall_{_i}.wav"
    synth(_line, _p, announce=False)
    STALL_WAVS.append(_p)
print("Ready.\n")

# ----------------------------------------------------------------------
# Main loop — sleep, wake on motion, hold one audience, re-arm for the next.
# ----------------------------------------------------------------------
print("Purrserpina sleeps. Walk up to wake her. (Ctrl+C to stop)\n")
try:
    while True:
        pir.wait_for_motion()
        hold_audience()

        sleep(0.5)
        eyes.off()                              # back to sleep
        print("...she sinks back into the dark.\n")

        # re-arm: wait for the porch to clear, settle, then accept the next mortal
        pir.wait_for_no_motion()
        sleep(COOLDOWN)
except KeyboardInterrupt:
    print("\nPurrserpina rests.")
finally:
    eyes.off()
    jaw.detach()
