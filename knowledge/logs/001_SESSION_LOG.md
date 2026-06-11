# 001_SESSION_LOG.md
## Session 1 — Phase 1 Implementation

**Date:** 2026-06-10
**Phase:** 1 — Skeleton, audio I/O, waveform + spectrum display, raw playback
**Status:** COMPLETE

---

## What Was Done

### Planning & Spec Clarification
Full feature specification discussed and locked. Key clarifications resolved:

- Zero-crossing detection: **linear sub-sample interpolation**
- Central ZC model: exactly one begin/center/end ZC per region; no two regions share a center ZC
- Pitch detection: **not needed** — pitch is inferred from ZC spacing
- Time-stretch: **pyrubberband** (Rubber Band Library) for quality
- Filter scope: applied to **exports AND original-file preview playback**; not re-applied during processed waveform playback
- Modify interpolation: begin = wave 0, end = wave N, **linear** across all
- Offset behaviour: **window shifts** around the fixed center ZC (center ZC identity does not change)
- Stereo: **left channel only**, no mixing
- Export: **plain numbered WAVs in ZIP**, no synth-specific metadata
- App name: **Wavebreach** (not WaveBreacher, not Wavebreacher)

Reference: PLANNING.md §12 (Open Questions Resolved)

### Files Created

| File | Purpose |
|---|---|
| `wavebreach.py` | Entry point — QApplication, stylesheet, font, command-line arg |
| `requirements.txt` | pip dependency list |
| `core/__init__.py` | Package marker |
| `core/state.py` | AppState and WaveRegion dataclasses |
| `core/audio_io.py` | Load, resample, mono, validate, export WAV |
| `core/playback.py` | PlaybackController wrapping sounddevice |
| `ui/__init__.py` | Package marker |
| `ui/styles.py` | LIGHT_STYLE and DARK_STYLE QSS strings |
| `ui/waveform_view.py` | Original waveform canvas widget |
| `ui/spectrum_view.py` | FFT spectrum canvas widget |
| `ui/param_panel.py` | Left-side parameter panel, all controls |
| `ui/playback_panel.py` | Right-side preview + export panel, CycleView |
| `ui/main_window.py` | MainWindow — layout, file load thread, raw playback |

### Architecture Established
- Strict `core/` vs `ui/` separation (no Qt in core)
- Single shared AppState passed by reference
- Two-tier update model documented (Tier 1 lightweight, Tier 2 Go-triggered)
- Background QThread for file loading
- All audio: float64, mono, 44100 Hz internally

### UI Confirmed Working
User confirmed the interface launched and displayed correctly on Windows with Anaconda.

---

## Issues Encountered

- `ui/styles.py` initially had a C-style `/* */` block comment at the top — Python
  syntax error. Fixed by converting to a Python docstring.
- Several Unicode em-dashes in `styles.py` caused `invalid character` syntax errors.
  Fixed by replacing all with `--`.
- Entry point file was initially named `wavebreacher.py`. Renamed to `wavebreach.py`
  and all internal references updated after user correction.

---

## Decisions Made This Session

| Decision | Detail |
|---|---|
| App name | Wavebreach (enforced — no -er suffix) |
| Font | IBM Plex Mono with Consolas fallback |
| Theme | Light default; dark swap via DARK_STYLE in styles.py |
| Canvas bg | Always dark (#121218) regardless of app theme |
| Waveform draw | 1px polyline with min/max per pixel column |
| Spectrum draw | Hann-windowed rfft, log-freq axis, filled silhouette |
| Waveform height | 160-220px (fixed range, expands to fill) |
| Spectrum height | 120-170px (fixed range) |

---

## Phase 2 Handoff Notes

The following stubs are in place ready for Phase 2:
- `WaveformView.set_regions()` — accepts selected_waves, excluded_min, excluded_max; drawing code is complete
- `MainWindow._on_params_changed()` — stub, needs ZC + splitter wired in
- `MainWindow._on_go()` — stub, needs Phase 3 DSP pipeline
- All overlay drawing in `waveform_view.py` is implemented; just needs data
