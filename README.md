# Wavebreach

Wavebreach is a dumb little utility for splitting an audio file into single-cycle waveforms to make a wavetable or bolognese or whatever. 
Maybe it will sound cool and be useful. Maybe it won't. Who knows!?!?

---

## Requirements

### Python
Python 3.10 or later recommended.

### Packages

**Using Anaconda (recommended on Windows):**
```bash
conda install -c conda-forge numpy scipy soundfile sounddevice pydub pyrubberband PySide6 ffmpeg rubberband
```

**Using pip:**
```bash
pip install -r requirements.txt
```

### System dependencies

| Dependency | Used for | Install |
|---|---|---|
| PortAudio | Audio playback (sounddevice) | Usually bundled with conda-forge sounddevice on Windows. Otherwise: `conda install -c conda-forge portaudio` |
| ffmpeg | MP3/M4A/AAC loading (pydub) | `conda install -c conda-forge ffmpeg` |
| rubberband | Time-stretching (Phase 3+) | `conda install -c conda-forge rubberband` |

If PortAudio is missing, the app will still open but playback buttons will be
disabled. A warning is shown in the status bar.

---

## Running

```bash
python wavebreach.py
```

Or pass an audio file directly:
```bash
python wavebreach.py /path/to/audio.wav
```

---

## Supported Input Formats

| Format | Notes |
|---|---|
| WAV | All sample rates and bit depths |
| AIFF / AIF | All sample rates |
| FLAC | All sample rates |
| OGG | Via soundfile |
| MP3 | Requires ffmpeg |
| M4A / AAC | Requires ffmpeg |
| WMA | Requires ffmpeg |

All input is converted internally to 44.1 kHz / mono / float64. Stereo and
multichannel files use the left channel only.

---

## Interface Overview

```
[ Waveform display — full width ]
  Path / Open / Play / Stop

[ Spectrum display — full width ]

[ Parameters (left) ]    [ Preview & Export (right) ]
  Start / End / Number     Single-cycle waveform view
  Min ZC / Max ZC          Prev / Next
  Length (Hz or samples)   Play All / Loop / Speed
  Filter (LP/HP/BP)        Wavetable name / Export ZIP
  Normalize
  Modify (Offset/Stretch/Suppress)
  [ GO ]
```

### Waveform display overlays
- **White lines** — begin/end zero-crossing of each selected waveform
- **Blue overlay** — selected waveform regions (will be exported)
- **Green overlay** — regions excluded by Min ZC parameter
- **Magenta overlay** — regions excluded by Max ZC parameter

---

## Parameters

| Parameter | Description |
|---|---|
| Start | Samples to skip at the front of the file |
| End | Samples to skip at the end of the file |
| Number | How many single-cycle waveforms to extract |
| Min ZC | Ignore zero-crossing gaps smaller than this (samples) |
| Max ZC | Ignore zero-crossing gaps larger than this (samples) |
| Length | Target length of each output waveform — set by pitch (Hz) or sample count |
| Filter | Resonant LP/HP/BP filter applied to each exported waveform |
| Normalize | Peak-normalize exported waveforms to target dB level |
| Offset | Shift the phase window position forward/backward across the wavetable |
| Stretch | Asymmetrically time-stretch the two halves of each waveform |
| Suppress | Volume-attenuate one half of each waveform |

Offset, Stretch, and Suppress each have Begin and End values that interpolate
linearly across all exported waveforms, creating gradual timbral evolution.

---

## Export

Click **Export ZIP** after pressing GO. You will be prompted for a save
location. The ZIP contains files named:

```
<wavetable_name>_0000.wav
<wavetable_name>_0001.wav
...
```

Each file is a single-cycle waveform at 44.1 kHz / 16-bit mono PCM.

---

## Project Structure

See `MEMORY.md` for the full directory layout and architecture notes.
See `PLANNING.md` for the full design and implementation plan.
