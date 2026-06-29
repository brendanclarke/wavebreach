# CLAUDE.md
## Agent Knowledge File — Wavebreach

This file is the primary reference for any AI agent working on this project.
It summarises the project's purpose, architecture, current state, conventions,
and known decisions so that context can be restored quickly at the start of
any session.

---

## Project Identity

**Name:** Wavebreach
**Entry point:** `wavebreach.py`
**Run with:** `python wavebreach.py` (or `python wavebreach.py /path/to/file.wav`)
**Purpose:** Desktop GUI utility that loads a short audio file (≤10s), slices
it into single-cycle waveforms at interpolated zero-crossings, applies
per-waveform DSP transforms, and exports a numbered, zipped set of WAV files
for use as a wavetable in a synthesizer.

---

## Directory Layout

```
wavebreach/
├── wavebreach.py              # Entry point — QApplication, MainWindow, bootstrap
├── requirements.txt           # pip deps (see also: conda notes in README.md)
├── README.md                  # Human-readable setup and usage guide
├── CLAUDE.md                  # This file — agent knowledge
├── PLANNING.md                # Full planning doc and phased implementation plan
│
├── core/                      # All DSP and data logic — no Qt imports allowed here
│   ├── __init__.py
│   ├── state.py               # AppState and WaveRegion dataclasses (shared state)
│   ├── audio_io.py            # Load, resample, convert, export WAV
│   ├── playback.py            # PlaybackController (sounddevice wrapper)
│   ├── zero_crossing.py       # [Phase 2] Interpolated ZC detection, min/max exclusion
│   ├── splitter.py            # [Phase 2] Waveform region selection algorithm
│   ├── modifier.py            # [Phase 3] Offset, Stretch, Suppress transforms
│   ├── filter_dsp.py          # [Phase 3] Resonant biquad filter design + application
│   ├── stretcher.py           # [Phase 3] Rubber Band time-stretch wrapper
│   └── exporter.py            # [Phase 5] ZIP + numbered WAV export
│
├── ui/                        # All Qt UI code — no DSP logic here
│   ├── __init__.py
│   ├── styles.py              # LIGHT_STYLE and DARK_STYLE QSS strings
│   ├── main_window.py         # MainWindow — layout orchestration, signal routing
│   ├── waveform_view.py       # Original waveform canvas (QPainter, dark bg)
│   ├── spectrum_view.py       # FFT spectrum canvas (log-freq, dB, silhouette)
│   ├── param_panel.py         # Left-side parameter panel (all controls)
│   └── playback_panel.py      # Right-side preview + export panel
│
└── knowledge/                 # Project knowledge base (not shipped to users)
    ├── logs/
    │   ├── 000_LOG_INDEX.md   # Index of all session logs
    │   └── 001_SESSION_LOG.md # Phase 1 session log
    └── (future: decisions/, references/)
```

---

## Architecture Principles

1. **Strict core/ui separation.** `core/` modules must not import from `ui/`.
   `ui/` modules may import from `core/`. This keeps DSP logic testable
   independently of Qt.

2. **Single shared AppState.** One `AppState` instance (defined in
   `core/state.py`) is created in `MainWindow.__init__` and passed by
   reference to all panels and core processors. No global variables.

3. **Two-tier update model.**
   - *Tier 1 (lightweight, immediate):* Parameter changes → re-run ZC
     detection + splitter → update waveform overlays. Runs on main thread.
   - *Tier 2 (heavy, Go-triggered):* Full DSP pipeline (Modify, stretch,
     filter, normalize) → runs in QThread with progress dialog.

4. **All audio internally float64, mono, 44100 Hz.** Input is converted on
   load. Export converts to int16 at write time.

5. **Left channel only for stereo/multichannel input.** No mixing, no
   channel selection.

---

## Key Design Decisions (Locked)

| Decision | Choice | Reason |
|---|---|---|
| GUI framework | PySide6 (Qt 6) | Mature, themeable, LGPL |
| Audio I/O | soundfile + pydub | soundfile for WAV/FLAC, pydub/ffmpeg for MP3/M4A etc |
| Playback | sounddevice | Low-latency, cross-platform PortAudio wrapper |
| Time-stretch | pyrubberband | High-quality phase vocoder, reliable Python bindings |
| Resampling | scipy.signal.resample_poly | Polyphase, high quality |
| FFT display | scipy.fft.rfft + Hann window | Standard, well-understood |
| Filter | Direct biquad (SVF formulation) | Resonant LP/HP/BP from one formula set |
| Filter order | 2-pole fixed | Not exposed; sufficient for wavetable preview |
| Stereo | Left channel only | Wavetables are mono; no stereo support needed |
| Export | Numbered WAVs in ZIP | Simple, universally compatible |
| Waveform draw | 1px polyline, min/max per column | Accurate transient representation |
| Spectrum draw | Filled silhouette | Visually clear for frequency content |
| Theme | Light default, dark swap-ready | QSS strings in ui/styles.py |
| Font | IBM Plex Mono (fallback: Consolas) | Industrial/utilitarian aesthetic |

---

## Zero-Crossing Model

- Interpolated detection: `zc_pos = i + s[i] / (s[i] - s[i+1])` for sign changes
- Each selected `WaveRegion` has exactly three ZCs: begin, center, end
- No two selected regions may share the same center ZC
- Regions overlapping `excluded_min` or `excluded_max` zones are skipped
- `excluded_min`: regions where consecutive ZC spacing < `min_samples`
- `excluded_max`: regions where consecutive ZC spacing > `max_samples`

## Offset Parameter Clarification

The Offset shifts the *window* around the fixed central ZC:
- At 0: window is `[begin_zc, end_zc]`
- At +0.5: window shifts forward — central ZC moves to the start of the frame
- At -0.5: window shifts backward — central ZC moves to the end of the frame
- The central ZC identity does not change; only the window position changes

---

## Implementation Phase Status

| Phase | Description | Status |
|---|---|---|
| 1 | Skeleton, audio I/O, waveform + spectrum display, raw playback | COMPLETE |
| 2 | ZC detection, splitter, live waveform overlays | COMPLETE |
| 2b | Interactive controls: zoom/pos sliders, draggable markers, spectrum drag | COMPLETE |
| 3 | Full DSP pipeline (Modify, stretch, filter, normalize), Go button | COMPLETE |
| 4 | Spectrum filter overlay | COMPLETE |
| 5 | Processed playback, Prev/Next, export ZIP | COMPLETE |
| 6 | Polish, validation, edge cases | TODO |
| 7 | User feedback round 1: filter contrast, Off mode, edge direction, avg length, CycleView fix | COMPLETE |
| 7 | User testing feedback round 1 (5 issues: filter overlay legibility, filter Off mode, length/pitch average display, edge-direction ZC filtering, CycleView scaling) | PLANNED (not yet implemented) |

---

## Dependencies

### pip / conda-forge
```
numpy scipy soundfile sounddevice pydub pyrubberband PySide6
```

### System-level (not pip)
- **PortAudio** — required by sounddevice. Usually bundled when installing
  sounddevice via conda-forge on Windows.
- **ffmpeg** — required by pydub for MP3/M4A/AAC. `conda install -c conda-forge ffmpeg`
- **rubberband-cli** — required by pyrubberband (Phase 3+).
  `conda install -c conda-forge rubberband`

### Conda one-liner
```bash
conda install -c conda-forge numpy scipy soundfile sounddevice pydub pyrubberband PySide6 ffmpeg rubberband
```

---

## Known Issues / Watch Points

- `sounddevice` will silently mark itself unavailable if PortAudio is missing.
  Play buttons are disabled in this case. Check status bar on launch.
- `pydub` format conversion requires ffmpeg on PATH. WAV/FLAC/AIFF load
  without it.
- `pyrubberband` is not used until Phase 3. Its absence will not affect
  Phase 1 or 2.
- The waveform pixel cache is invalidated on resize — this is intentional and
  correct but means a brief repaint on window resize for long files.
- Tier-1 updates (ZC + splitter) run on the main thread. If profiling shows
  lag on maximal-length files, move to a QThread.
- **[CONFIRMED BUG, see PLANNING.md Phase 7.1]** Spectrum filter overlay
  (`ui/spectrum_view.py :: _draw_filter_overlay`) is rendered correctly but
  too faintly (alpha=55) to read against the raw spectrum fill underneath
  it. The filter response data updates correctly on every cutoff/Q change;
  only the visual contrast is wrong. Do not "fix" the data pipeline for
  this issue -- it is a rendering/contrast problem only.
- **[CONFIRMED BUG, see PLANNING.md Phase 7.5]** `CycleView`
  (`ui/playback_panel.py`) stretches any array to fill its pixel width with
  no length validation or visual reference. Before fixing the display,
  verify `core/processor.py` is actually producing `target_len`-sample
  waveforms (add an assertion) to rule out a silent upstream length defect.
- **[PLANNED, not yet built, see PLANNING.md Phase 7.4]**
  `core/zero_crossing.py :: detect()` currently returns position-only data
  with no slope/direction. Edge-direction filtering (Rising/Falling/None)
  requires extending this return type -- check call sites in
  `core/splitter.py` and `core/zero_crossing.py :: filter_usable()` if
  modifying the return signature.
