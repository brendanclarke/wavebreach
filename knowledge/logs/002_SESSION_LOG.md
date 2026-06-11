# 002_SESSION_LOG.md
## Session 2 -- Phase 2 Implementation

**Date:** 2026-06-10
**Phase:** 2 -- ZC detection, splitter, live waveform overlays
**Status:** COMPLETE

---

## What Was Done

### Documentation Added
- `CLAUDE.md` -- agent knowledge file (directory layout, architecture,
  design decisions, phase status, dependency notes)
- `README.md` -- human-readable setup, usage, parameter reference
- `PLANNING.md` -- full spec, algorithm descriptions, phased plan with
  status markers
- `knowledge/logs/000_LOG_INDEX.md` -- session log index with
  knowledge cross-references
- `knowledge/logs/001_SESSION_LOG.md` -- Phase 1 session log
- `knowledge/logs/002_SESSION_LOG.md` -- this file

### Files Created

| File | Purpose |
|---|---|
| `core/zero_crossing.py` | Interpolated ZC detection, exclusion zone computation, usable ZC filter |
| `core/splitter.py` | WaveRegion selection: triplet enumeration, ideal-position matching, center-ZC deduplication |

### Files Updated

| File | Changes |
|---|---|
| `ui/main_window.py` | Added `_run_tier1()` -- ZC detect + exclusion + splitter + overlay push. Wired to `_on_params_changed()`, `_on_load_finished()`, and `_on_go()`. Added Phase 2 imports. Removed leftover `import os`. |

---

## Algorithm Details

### Zero-Crossing Detection (`core/zero_crossing.py`)

Three functions:

**`detect(samples)`**
- Iterates adjacent sample pairs
- For sign changes: `zc = i + s[i] / (s[i] - s[i+1])`
- Exact zeros: included if not part of a flat-zero run (only first sample
  of a run is marked)
- Returns sorted list of float positions

**`compute_exclusions(zc_list, min_samples, max_samples)`**
- Min: finds runs of consecutive ZCs with spacing < min_samples,
  merges them into regions, adds half-min_samples buffer either side
- Max: any gap > max_samples becomes a max-excluded region
- Returns (excluded_min, excluded_max) as lists of (float, float) tuples

**`filter_usable(zc_list, excluded_min, excluded_max, start_pad, end_pad, total)`**
- Removes ZCs outside [start_pad, total-end_pad]
- Removes ZCs inside any excluded region
- Returns clean list ready for the splitter

### Splitter (`core/splitter.py`)

**`select_regions(usable_zcs, num_waves, start_pad, end_pad, total_samples)`**
- Enumerates all adjacent triplets (begin, center, end) from usable ZCs
- Computes num_waves evenly-spaced ideal positions across the work region
- Greedy nearest-match: each ideal position claims the triplet with the
  nearest center ZC
- Deduplication: collisions on rounded center ZC integer -> keep the
  closer one, drop the other (slot goes empty, count may be < num_waves)
- Returns sorted list of WaveRegion objects

### Tier-1 Live Update (`ui/main_window.py :: _run_tier1`)

Called on:
- File load complete
- Any parameter widget change (via `params_changed` signal)
- GO button press (before Phase 3 DSP)

Pipeline:
1. `detect(raw_samples)` -> all ZCs
2. `compute_exclusions(...)` -> excluded_min, excluded_max
3. `filter_usable(...)` -> usable ZCs
4. `select_regions(...)` -> WaveRegion list
5. `wave_view.set_regions(...)` -> repaints overlays
6. Status bar updated with counts

All runs synchronously on the Qt main thread. Expected to be fast enough
(<50ms) for files up to 441,000 samples. If profiling shows lag, move to
QThread in Phase 6.

---

## Issues / Notes

- The `_on_params_changed` handler now calls `read_into_state()` before
  `_run_tier1()`, so AppState is always current before the ZC pass runs.
- The `_on_go` handler also calls `_run_tier1()` to ensure the overlay
  is up to date before Phase 3 DSP runs on that state.
- Unicode special characters (arrows, em-dashes) removed from button
  labels in main_window.py to avoid any platform font issues.

---

## Phase 3 Handoff Notes

Ready for Phase 3:
- `AppState.selected_waves` is always populated after Tier-1 runs
- `WaveRegion` objects have `begin_sample` / `end_sample` integer indices
  ready for numpy array slicing
- `AppState.length_mode`, `length_hz`, `length_samples` are set from UI
- `AppState.filter_mode`, `filter_cutoff`, `filter_q` are set from UI
- `AppState.offset_begin/end`, `stretch_begin/end`, `suppress_begin/end`
  are set from UI
- `MainWindow._on_go()` stub is wired and calls `read_into_state()` +
  `_run_tier1()` before handing off to Phase 3 DSP worker
