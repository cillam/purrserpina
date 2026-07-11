import subprocess
import wave
from piper import PiperVoice, SynthesisConfig

VOICE  = "/home/cillam/piper-voices/en_US-kristin-medium.onnx"
SAMPLE = ("Ahh. Come closer, mortal. The veil is thin tonight... "
          "and I foresee a great and terrible shortage of candy in your future.")

# current voice character — starts at Piper's defaults
settings = {
    "volume":        1.0,     # 0.0–1.0
    "length_scale":  1.0,     # speed: higher = slower
    "noise_scale":   0.667,   # expressiveness
    "noise_w_scale": 0.8,     # rhythm variation
}
reverb = False                # crypt echo on the output

print("Loading Purrserpina's voice...")
voice = PiperVoice.load(VOICE)
print("Ready.")

def speak(text):
    syn = SynthesisConfig(
        volume=settings["volume"],
        length_scale=settings["length_scale"],
        noise_scale=settings["noise_scale"],
        noise_w_scale=settings["noise_w_scale"],
        normalize_audio=True,
    )
    with wave.open("/tmp/voice_test.wav", "wb") as wav:
        voice.synthesize_wav(text, wav, syn_config=syn)
    cmd = ["ffplay", "-autoexit", "-nodisp", "-loglevel", "quiet"]
    if reverb:
        cmd += ["-af", "aecho=0.8:0.9:60:0.3"]   # vast, cold-room echo
    cmd.append("/tmp/voice_test.wav")
    subprocess.run(cmd)

def show():
    print(f"  volume={settings['volume']}  length_scale={settings['length_scale']}  "
          f"noise_scale={settings['noise_scale']}  noise_w_scale={settings['noise_w_scale']}  "
          f"reverb={'on' if reverb else 'off'}")

HELP = """
Commands:
  (press Enter)       speak the sample line with current settings
  <any text>          speak your own line
  vol N               volume        (0.0-1.0)
  len N               length_scale  (speed; higher = slower)
  noise N             noise_scale   (expressiveness)
  noisew N            noise_w_scale (rhythm)
  reverb on | off     toggle crypt echo
  show                print current settings
  reset               back to Piper defaults
  q                   quit
"""
print(HELP)
show()

ALIASES = {"vol": "volume", "len": "length_scale",
           "noise": "noise_scale", "noisew": "noise_w_scale"}

while True:
    try:
        line = input("\nvoice> ").strip()
    except (EOFError, KeyboardInterrupt):
        break

    if line in ("q", "quit", "exit"):
        break
    elif line == "":
        speak(SAMPLE)
    elif line == "show":
        show()
    elif line == "reset":
        settings.update(volume=1.0, length_scale=1.0,
                        noise_scale=0.667, noise_w_scale=0.8)
        reverb = False
        show()
    elif line.startswith("reverb"):
        parts = line.split()
        reverb = len(parts) > 1 and parts[1].lower() in ("on", "true", "1", "yes")
        show()
    elif line.split()[0] in ALIASES:
        parts = line.split()
        try:
            settings[ALIASES[parts[0]]] = float(parts[1])
            show()
        except (IndexError, ValueError):
            print("  ?  usage: <param> <number>   e.g.  len 1.3")
    else:
        speak(line)
