# 005_SESSION_LOG.md
## Session 5 -- Phase 7: User Feedback Round 1 Fixes

**Date:** 2026-06-22
**Phase:** 7 -- Bug fixes and new features from user testing
**Status:** COMPLETE

---

## Changes Made

### 7.1 -- Filter overlay contrast fix (BUG)
`ui/spectrum_view.py`:
- Raw spectrum dimmed when filter is active (alpha 100/35 vs 180/60).
- Filter overlay colour changed to amber (QColor 0xFF,0xA0,0x20 alpha 110).
- Response curve line weight: 2px, brightened to 0xFF,0xC0,0x40 alpha 220.
- When Off: full-brightness spectrum, all filter elements hidden.

### 7.2 -- Filter Off mode (NEW)
- `core/state.py`: filter_mode now accepts "OFF".
- `ui/param_panel.py`: Off radio button added; cutoff/Q controls disabled when Off.
- `core/processor.py`: sos=None when OFF; apply step skipped.
- `ui/main_window.py`: playback and display both bypass filter when OFF.

### 7.3 -- Average region length diagnostic (NEW)
- `ui/param_panel.py`: avg length label at bottom of LENGTH group.
- `set_avg_length(avg_samples)` public method.
- `ui/main_window.py`: _run_tier1() computes and pushes avg after each pass.

### 7.4 -- Edge direction filtering (NEW)
- `core/zero_crossing.py`: detect() returns list[tuple[float, bool]].
  True=rising (neg->pos), False=falling (pos->neg).
  compute_exclusions() and filter_usable() updated accordingly.
  filter_usable() gains edge_mode='none'|'rising'|'falling'.
- `core/splitter.py`: select_regions() gains edge_mode; filters center ZC direction.
- `core/state.py`: edge_mode field added.
- `ui/param_panel.py`: Edge None/Rising/Falling radio buttons at top of SLICE.
- `ui/main_window.py`: _run_tier1() passes edge_mode to filter_usable and select_regions.

### 7.5 -- CycleView scaling and length verification (BUG + DISPLAY)
- `core/processor.py`: length assertion post-pipeline; logs WARNING and corrects.
- `ui/playback_panel.py`: CycleView rewritten with min/max per column,
  quarter-cycle grid lines, sample count label bottom-right.

---

## Test Results

All checks passed:
- ZC: 880 total, 440 rising, 440 falling on 440Hz sine
- filter_usable: none=880, rising=440, falling=440
- select_regions: 16 for all three edge modes
- Processor filter=OFF: 8 waves x 100 smp OK
- Processor rising+LP: 4 waves x 100 smp OK
- Avg length: 100.2 smp (expected 100.2 for 440Hz@44100Hz) OK

---

## Files Modified

| File | Changes |
|---|---|
| `core/zero_crossing.py` | detect() returns (pos, is_rising); filter_usable() edge_mode |
| `core/splitter.py` | select_regions() edge_mode; center ZC direction filter |
| `core/state.py` | edge_mode field; filter_mode comment updated |
| `core/processor.py` | Filter OFF bypass; length verification + correction |
| `ui/param_panel.py` | Edge radio buttons; Off filter button; avg length label |
| `ui/main_window.py` | _run_tier1() edge_mode + avg length; filter Off handling |
| `ui/spectrum_view.py` | Dimmed spectrum; amber overlay; hide all when Off |
| `ui/playback_panel.py` | CycleView: min/max drawing, grid, sample count label |

---

## Addendum: Bug Fixes Applied After Initial Phase 7 (same session)

### Bug A -- Edge mode doubled region width
**Root cause:** `filter_usable()` was stripping ZCs by direction before the
splitter ran. With only rising ZCs in the list, adjacent triplets
(i, i+1, i+2) spanned two full cycles instead of one.

**Fix:** Removed direction filter from `filter_usable()` entirely.
The function now returns all non-excluded ZCs in the work region,
regardless of `edge_mode`. Direction filtering of the *center* ZC only
happens inside `select_regions()`, which already had it correctly.
`edge_mode` parameter retained in `filter_usable()` signature for API
compatibility but is now a no-op there.

**Verified:** All three edge modes produce avg region spans of 100.2 smp
(one cycle of 440 Hz at 44100 Hz). Rising centers are all rising,
falling centers are all falling.

### Bug B -- No real time-stretch (scipy fallback was a resample)
**Root cause:** `stretcher.py` fell back to `scipy.signal.resample_poly`
when pyrubberband was unavailable. This is not a time-stretch -- it
changes pitch as well as duration, producing incorrect wavetable output.

**Fix:**
1. Installed `pyrubberband` (pip) and `rubberband-cli` (apt) in the
   development environment. Both confirmed working.
2. Removed the scipy fallback entirely. `stretch()` now raises a clear
   `RuntimeError` with install instructions if pyrubberband is missing.
3. Fixed pyrubberband ratio convention: `pyrb.time_stretch(audio, sr, r)`
   uses a *speed* ratio where r=2.0 = 2x faster = shorter output.
   Our public API uses *length* ratio (>1 = longer), so we invert:
   `speed_ratio = 1.0 / length_ratio`.

**Verified:** 2x stretch: 2000 -> 4000 smp. 0.5x: 2000 -> 1000 smp.
Pitch preserved: 440 Hz input peaks at 441 Hz after 2x stretch (FFT
resolution limited). `stretch_to_length()` exact for 100/256/512/2048 smp.
Full pipeline with rubberband + rising edge + LP filter produces
non-silent output at correct length.

### requirements.txt updated
Added `pyrubberband>=0.3.0` (was already there) and note that
`rubberband-cli` system package is required.

---

## Addendum B: Length Normalisation Algorithm Change

**Problem:** Rubber Band (phase vocoder) produced a "pulse that decays to
silence" when asked to stretch a ~169-sample single-cycle slice to 2000
samples. Root cause: the input is shorter than one analysis frame (~1024
samples), so the phase vocoder has no spectral content to synthesise from.

**Conceptual correction:** For wavetable export, length normalisation is not
a time-stretch -- it is a **resample of the waveform shape**. The synth
determines pitch by how fast it cycles through the table; the tool's job is
only to define the shape across N samples. Simple interpolation is correct,
complete, and artifact-free.

**Fix:** Replaced `stretcher.stretch_to_length()` in `processor.py` with
`numpy.interp`:
```python
x_old = np.linspace(0.0, 1.0, len(chunk))
x_new = np.linspace(0.0, 1.0, target_len)
wave  = np.interp(x_new, x_old, chunk)
```
`stretcher` import removed from `processor.py`. Rubber Band is still used
by `modifier.py` for the asymmetric Stretch transform (which IS a
time-stretch in the traditional sense).

**Verified:** 169-sample sine slice resampled to 169, 512, and 2000 samples.
All three outputs: peak at 25%, trough at 75%, exactly 1 zero-crossing,
min=-1.0, max=1.0. Shape is identical across all target lengths.

---

## Addendum C: Distribute modifier added

New fourth Modify option: **Distribute** (Begin/End, -0.5 to +0.5).

After Offset, Stretch, and Suppress have run, the calculated position of
the central ZC within the chunk is used to split it into two halves.
Each half is resampled via np.interp to a new sample count; the two halves
are concatenated to give the same total length as the input.

- +0.5: first half grows by 50% of its length, second half shrinks to compensate
- -0.5: first half shrinks by 50% of its length, second half grows to compensate
- 0.0: no change

The center position used is the *calculated* position tracked through Offset
and Stretch transforms -- not a new zero-crossing detection. This matches
the user's specification exactly.

Files changed: core/modifier.py, core/state.py, core/processor.py,
ui/param_panel.py.

Verified: +0.5 moves first-half peak to 75% of frame, -0.5 to 25%.
Output length exact (200 smp) for all distribute values.
