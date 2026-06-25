# PLANNING.md
## Wavebreach — Design & Implementation Plan

This document records all design decisions made during the planning session,
the full feature specification, and the phased implementation plan.
It may be marked up as phases are completed.

Status markers: `[DONE]` `[IN PROGRESS]` `[TODO]`

---

## 1. Project Brief

Convert short audio files (up to 10 seconds, any common format) into indexed
sets of single-cycle waveforms for use as wavetables in software synthesizers.

The output is a ZIP file of numbered 44.1 kHz / 16-bit mono WAV files.

---

## 2. Input Handling

- Accept any common audio format (WAV, AIFF, FLAC, OGG, MP3, M4A, AAC, WMA)
- Convert anything not already 44.1 kHz / 16-bit PCM on load
- Stereo or multichannel: use left channel only, no mixing
- Maximum duration: 10 seconds (441,000 samples at 44.1 kHz)
- Reject files over 10 seconds with a user-facing error dialog

---

## 3. Interface Layout

```
+---------------------------------------------------------------+
|  [ WAVEFORM VIEW — full width ]                               |
|  Path label              [Open]  [Play]  [Stop]               |
+---------------------------------------------------------------+
|  [ SPECTRUM VIEW — full width ]                               |
+---------------------------+-----------------------------------+
|  PARAMETERS (left)        |  PREVIEW (right)                  |
|                           |                                   |
|  Start:   [___] smp       |  [ SINGLE-CYCLE VIEW ]            |
|  End:     [___] smp       |  Wave 0001 / 0042                 |
|  Number:  [___]           |  [Prev]  [Next]                   |
|  Min ZC:  [___] smp       |                                   |
|  Max ZC:  [___] smp       |  [Play All]  [Loop]               |
|                           |  Speed: [----o----] 1.00x         |
|  Length:                  |                                   |
|   o Pitch:   [___] Hz     |  Name: [___________]              |
|   * Samples: [___]        |  [Export ZIP]                     |
|                           |                                   |
|  Filter: o LP  * HP  o BP |                                   |
|  Cutoff: [___] Hz         |                                   |
|  Q:      [___]            |                                   |
|                           |                                   |
|  Normalize: [x] [___] dB  |                                   |
|                           |                                   |
|  Modify:   Begin   End    |                                   |
|  Offset:  [___]  [___]    |                                   |
|  Stretch: [___]  [___]    |                                   |
|  Suppress:[___]  [___]    |                                   |
|                           |                                   |
|  [ GO ]                   |                                   |
+---------------------------+-----------------------------------+
```

---

## 4. Display Elements

### 4.1 Waveform Display (top, full width)
- Dark canvas background always, regardless of app theme
- Waveform drawn as 1px polyline (min/max per pixel column for accuracy)
- Updates live as parameters change
- **White lines:** 1px vertical lines at begin/end ZC of each selected region
- **Blue semi-transparent overlay:** selected regions (between split lines)
- **Green semi-transparent overlay:** regions excluded by Min ZC
- **Magenta semi-transparent overlay:** regions excluded by Max ZC
- File playback with filter applied (Phase 3+)

### 4.2 Spectrum Display (below waveform, full width)
- FFT of loaded file: Hann-windowed, log-frequency X axis (20Hz-22050Hz), dB Y axis
- Drawn as filled silhouette
- **Blue semi-transparent overlay:** filter response curve (Phase 3+)
  Represents pass band, slope, and resonance peak

### 4.3 Single-Cycle Preview (right panel)
- Displays one processed waveform at a time
- Green line colour (to distinguish from main waveform view)
- Prev/Next buttons cycle through all processed waveforms

---

## 5. Processing Parameters (full specification)

### Edge (added Phase 7)
Horizontal radio button group at top of SLICE panel: Rising / Falling / None.
Constrains which zero-crossings are eligible to serve as a region's
**central** ZC, based on slope direction at the crossing.
- **None** (default): no constraint -- any ZC may be central (current/original behaviour)
- **Rising**: only negative-to-positive transitions eligible as central ZC
- **Falling**: only positive-to-negative transitions eligible as central ZC
- Begin/end ZCs of a region are unconstrained -- only the central ZC is filtered

### Start
Samples padded/skipped at front of file before first waveform selection.

### End
Samples padded/skipped at end of file before last waveform selection.

### Number
How many single-cycle waveforms to extract between Start and End.
Actual count may be less if insufficient usable ZC triplets exist.

### Min ZC (samples)
Ignore regions where consecutive zero-crossings are closer than this.
Used to exclude noise, DC offsets, high-frequency hash.
Excluded regions shown as green overlay.

### Max ZC (samples)
Ignore regions where consecutive zero-crossings are farther apart than this.
Used to exclude silence or sub-sonic content.
Excluded regions shown as magenta overlay.

### Length
Target output length for all exported waveforms.
Two modes (radio button, one active, other is display-only and updates live):
- **Pitch (Hz):** 20-20000 Hz. Length = 44100 / Hz samples.
- **Samples:** 1-441000. Direct sample count.

All waveforms are time-stretched to this length after slicing.

### Filter
Resonant multi-mode filter applied to each exported waveform.
Also applied to original-file preview playback.
- **Mode:** LP / HP / BP / Off (radio button) -- Off added Phase 7
- **Cutoff:** 20-22000 Hz. Defined as the -3dB (half-power) point.
  Beyond cutoff, the 2-pole filter rolls off at 12 dB/octave (not a hard
  wall). Confirmed acceptable definition in Phase 7 review.
- **Q:** 0.1-10.0 (resonance; 0.707 = Butterworth / no resonance)
- **Implementation:** Direct SVF biquad formulation, 2-pole fixed
- Shown as semi-transparent overlay on spectrum display
  (legibility fix pending -- see Phase 7.1)

### Normalize
Peak normalization of exported waveforms.
- **Enable:** checkbox
- **Target:** 0.0 to -3.0 dB in 0.1 dB steps

### Modify
Three transforms, each with Begin and End values.
Values interpolate linearly across the exported wavetable:
`param[k] = begin + (k / (K-1)) * (end - begin)`

#### Offset (-0.5 to +0.5)
Shifts the sample window around the fixed central ZC.
- 0: window is [begin_zc, end_zc], central ZC centred
- +0.5: window shifts forward — central ZC at start of frame
- -0.5: window shifts backward — central ZC at end of frame
The central ZC identity does not change; the window moves around it.

#### Stretch (-0.5 to +0.5)
Asymmetric time-stretch of the two halves (split at central ZC).
- 0: no change
- +0.5: first half compressed 50%, second half stretched to compensate
- -0.5: first half stretched, second half compressed
Applied via Rubber Band before final length normalisation stretch.

#### Suppress (-1.0 to +1.0)
Volume reduction of one half of the waveform.
- 0: no change
- +1.0: first half (before central ZC) fully attenuated
- -1.0: second half (after central ZC) fully attenuated
Applied as a ramp to avoid hard clicks at the central ZC.

---

## 6. Zero-Crossing Algorithm

### Detection
Interpolated sub-sample precision:
```
zc_pos = i + s[i] / (s[i] - s[i+1])   for sign changes (s[i]*s[i+1] < 0)
```
Exact zeros (s[i] == 0) added as integer crossings.

### Exclusion
- **Min exclusion:** runs of ZCs where spacing < min_samples → excluded_min regions
- **Max exclusion:** gaps between ZCs > max_samples → excluded_max regions

### WaveRegion Selection
1. Collect all valid ZCs (not in excluded regions, within start/end bounds)
2. Enumerate candidate triplets (begin_zc, center_zc, end_zc)
3. Compute N evenly-spaced ideal positions between start and end
4. Greedy nearest-match: assign each ideal position to the nearest valid triplet
5. Deduplicate: no two regions may share a center_zc
   - On collision: drop the region with larger distance from ideal position
6. Result: ordered list of WaveRegion objects (may be < requested number)

---

## 7. DSP Pipeline (Phase 3)

Order of operations per waveform, applied after slicing:
1. Offset transform (window shift)
2. Stretch transform (asymmetric time-compress/expand via Rubber Band)
3. Length normalisation (Rubber Band stretch to target sample count)
4. Filter (biquad sosfilt)
5. Normalize (peak scale to target dB)

---

## 8. Export (Phase 5)

- Each waveform: float64 → int16 → soundfile.write() → BytesIO
- ZIP assembled in memory: `<name>_XXXX.wav` (zero-padded, min 4 digits)
- Save path via QFileDialog.getSaveFileName
- ZIP written to chosen path

---

## 9. Technology Stack

| Role | Library | Notes |
|---|---|---|
| GUI | PySide6 (Qt 6) | LGPL, full QSS theming |
| Audio load | soundfile | WAV/AIFF/FLAC/OGG |
| Audio load (other) | pydub + ffmpeg | MP3/M4A/AAC/WMA |
| Playback | sounddevice | PortAudio wrapper |
| Resampling | scipy.signal.resample_poly | Polyphase |
| FFT | scipy.fft.rfft | Hann-windowed |
| Filter | scipy.signal.sosfilt | Direct biquad SOS |
| Time-stretch | pyrubberband | Rubber Band Library |
| Export | soundfile + zipfile | Standard library ZIP |

---

## 10. Phased Implementation Plan

### Phase 1 — Skeleton, audio I/O, waveform + spectrum display [DONE]
- Project structure and all empty module stubs
- `core/state.py`: AppState and WaveRegion dataclasses
- `core/audio_io.py`: load, convert, resample, mono, validate
- `core/playback.py`: PlaybackController (sounddevice wrapper)
- `ui/styles.py`: LIGHT_STYLE and DARK_STYLE QSS
- `ui/waveform_view.py`: dark canvas, 1px polyline, min/max downsampling
- `ui/spectrum_view.py`: FFT silhouette, log-freq axis, dB axis, grid
- `ui/param_panel.py`: all controls, correct types/ranges, GO button
- `ui/playback_panel.py`: CycleView, nav buttons, speed slider, export controls
- `ui/main_window.py`: full layout, file open, background load thread, raw play
- `wavebreach.py`: QApplication, stylesheet, command-line file arg

### Phase 2 — ZC detection, splitter, live waveform overlays [DONE]
- `core/zero_crossing.py`: interpolated detection, min/max exclusion zones
- `core/splitter.py`: WaveRegion selection, deduplication
- Wire param changes to Tier-1 update (ZC + splitter on main thread)
- Waveform view: draw split lines, blue/green/magenta overlays live

### Phase 2b — Interactive controls [DONE]
- `ui/waveform_view.py`: Zoom slider (1x-50x log) + Position slider below canvas
- `ui/waveform_view.py`: Draggable Start (orange) and End (cyan) markers on canvas
  - Hit zone 8px, cursor feedback, emits `start_changed(int)` / `end_changed(int)`
- `ui/spectrum_view.py`: Draggable cutoff handle (amber line + diamond)
  - Left/right drag: cutoff frequency (log-scale, full range = full widget width)
  - Up/down drag: Q (150 px/decade, slow response)
  - Emits `cutoff_changed(float)` / `q_changed(float)`
- `ui/param_panel.py`: Log-scale QSliders for Cutoff (20-22000 Hz) and Q (0.1-10)
- `ui/param_panel.py`: Integer QSliders for Start and End (range set on file load)
- All controls bidirectionally wired via blockSignals guards (no feedback loops)
- `MainWindow` routes: canvas drag -> param panel; spectrum drag -> param panel;
  param changes -> spectrum display sync; param changes -> waveform marker sync

### Phase 3 -- Full DSP pipeline [DONE]
- `core/filter_dsp.py`: SVF biquad design (LP/HP/BP), sosfilt, compute_response
- `core/stretcher.py`: pyrubberband wrapper with scipy fallback
- `core/modifier.py`: Offset, Stretch, Suppress per-waveform transforms
- `core/processor.py`: ProcessWorker -- full pipeline orchestrator
- `ui/main_window.py`: Go -> QThread + QProgressDialog; filtered preview playback
- `ui/param_panel.py`: Start/End sliders repositioned directly under spinboxes

### Phase 4 -- Spectrum filter overlay [DONE]
- `ui/spectrum_view.py`: filter response drawn as filled blue overlay + curve
- Response updated live on every filter param change via MainWindow._sync_filter_display()

### Phase 5 — Processed playback, navigation, export [TODO]
- `core/exporter.py`: ZIP assembly, numbered WAV naming
- `ui/playback_panel.py`: fully wire Prev/Next, Play All, Loop, Speed
- `ui/main_window.py`: wire export dialog and exporter
- Playback of processed waves (no filter re-applied)

### Phase 6 — Polish and validation [TODO]
- Input validation with red-border feedback on invalid combos
- Edge case error dialogs (no usable ZCs, stretch ratio limits, etc.)
- Status bar messaging throughout pipeline
- Final integration testing with real audio files
- README review and dependency instruction verification

### Phase 7 — User Testing Feedback Round 1 [DONE]
Issues identified by user testing the Phase 3 build (screenshot-driven review).
Each item tagged `[BUG]` (existing code not behaving as designed) or `[NEW]`
(functionality not yet built, was out of scope until now).

**Cutoff definition (resolved in discussion):** cutoff = the -3dB point
(half-power / ~71% amplitude). Beyond cutoff, a 2-pole filter rolls off at
12 dB/octave -- not a hard wall, but a defined, standard slope. Confirmed
acceptable by user; no change to the underlying filter math.

#### 7.1 Filter cutoff display bug `[BUG]`
**Symptom:** dragging the cutoff handle on the spectrum view moves the
amber marker line and label, but the visible "hump" of energy in the
spectrum display does not appear to move, making it look like the filter
isn't responding.

**Root cause (confirmed by code trace):** the spectrum view draws two
independent things stacked on the same canvas:
  1. The raw file's FFT silhouette (`_draw_spectrum`) -- this is the
     harmonic content of the loaded audio itself and is correctly static;
     it should NOT move when the filter changes.
  2. The filter frequency response overlay (`_draw_filter_overlay`) -- this
     DOES update correctly on every cutoff/Q change (verified: the signal
     chain `spectrum drag -> param_panel.set_cutoff() -> state.filter_cutoff
     -> MainWindow._sync_filter_display() -> spec_view.set_filter_response()`
     round-trips correctly).

The actual defect is **rendering legibility**: the filter overlay
(`FILTER_OVERLAY = QColor(0x64, 0xB4, 0xFF, 55)`, alpha 55/255) is too faint
against the dominant raw spectrum fill to read as a distinct, moving shape.
The data is correct; the visual presentation fails to communicate it.

A secondary contributing factor: at Q values below 0.707 (the Butterworth
point), the 2-pole biquad response is broad and gently sloped rather than a
sharp "wall," which can look like "nothing is happening" even when the
response has moved, especially when half-buried under the raw spectrum.

**Fix direction (Phase 7 implementation):**
- Increase contrast between raw spectrum and filter overlay (e.g. dim the
  raw spectrum fill further when a filter is active and not bypassed,
  and/or draw the filter response line with a bolder stroke / higher
  contrast colour).
- Consider drawing the filter response as the dominant visual element
  rather than a thin overlay, since it's the actionable, user-controlled
  element.
- No change needed to the underlying filter math -- cutoff definition
  confirmed correct as the -3dB point.

#### 7.2 Filter Off mode `[NEW]`
Add a fourth filter mode: **Off** (bypass). Alongside LP / HP / BP as a
fourth radio button.
- When Off is selected: `core/processor.py` skips `filter_dsp.apply_filter()`
  entirely for exported waveforms.
- `MainWindow._on_play_original()` skips filter application for preview
  playback when Off is selected.
- Spectrum view filter overlay either hidden or shown as a flat 0dB line
  when Off is active.
- `AppState.filter_mode` gains a fourth valid value: `"OFF"`.

#### 7.3 Length / Pitch average display `[NEW]`
When Start, End, Min ZC, Max ZC, or Number change (i.e. whenever the
splitter reselects regions), the Length group's non-active field should
update to show the **average** actual cycle length/pitch across all
currently selected regions -- not just echo the user's last typed value.

- If "Pitch (Hz)" is the active radio button: the Hz field remains
  user-editable as today, but the **Samples** display should additionally
  reflect... (need to clarify: does the user want the *target* samples
  value used for stretching, which is already derived from Hz exactly via
  `44100/Hz`, OR do they want a *diagnostic* readout of what the average
  raw region length currently is, before stretching, so they can see how
  far off the source material is from their target? Based on context this
  reads as the latter -- a diagnostic/informational average, not the
  stretch target. This needs one clarifying question before implementation.)
- Likely implementation: `MainWindow._run_tier1()` computes
  `avg_length_samples = mean(region.end_zc - region.begin_zc for region in
  selected_waves)` and pushes it to a new informational label in
  `ParamPanel` (distinct from the existing Hz/Samples target fields, to
  avoid overwriting the user's input).

#### 7.4 Edge-direction filtering for zero-crossing selection `[NEW]`
Add a horizontal radio button group at the top of the SLICE panel:
**Edge: Rising / Falling / None**

- **None** (default): current behaviour, unchanged -- any zero-crossing
  may serve as a central ZC regardless of slope direction.
- **Rising**: only zero-crossings where the signal transitions from
  negative to positive (slope > 0 at the crossing) are eligible as a
  *central* ZC for a selected region.
- **Falling**: only zero-crossings where the signal transitions from
  positive to negative (slope < 0) are eligible as a central ZC.
- Begin/end ZCs of a region are unaffected by this filter -- only the
  central ZC's direction is constrained, per the user's wording
  ("central zero-crossing edges should be falling/rising").

**Implementation scope (confirmed by code trace):**
`core/zero_crossing.py :: detect()` currently returns only float positions,
with no slope/direction metadata. This needs to change to return direction
alongside position (e.g. a list of `(position, is_rising)` tuples, or a
parallel array). `core/splitter.py :: select_regions()` needs a new
`edge_mode` parameter that filters candidate triplets by the direction of
the triplet's center ZC before the nearest-match assignment step.

#### 7.5 Single-cycle preview scaling bug `[BUG]`
**Symptom:** the single-cycle waveform preview (right panel, `CycleView`)
does not appear to show a clean, correctly-scaled single cycle matching the
configured Length parameter -- the displayed shape looks stretched or
arbitrary rather than a clear periodic waveform of the expected length.

**Root cause (confirmed by code trace):** `CycleView.paintEvent()` maps
whatever array it is given to the full widget pixel width using simple
proportional index mapping (`idx = int(x / w * n)`), with **no validation
or visual reference for the actual sample count** `n`. This means:
  1. If the processed waveform genuinely is `length: smp` samples (which it
     should be, since `core/processor.py` calls
     `stretcher.stretch_to_length(chunk, target_len, sr)` for every region),
     the display will still look "correct" in the sense of filling the
     window, but gives the user no way to visually confirm the sample count
     or judge whether the shape is a clean single cycle.
  2. If the processed waveform is NOT actually `target_len` samples (a
     possible defect in the modifier/stretch chain producing malformed
     output), this display bug would mask that defect, since any array
     length is stretched to fill the same visual space identically.

**This needs verification, not just a display fix.** Before correcting
`CycleView`, Phase 7 implementation should add an assertion / debug check
in `core/processor.py` confirming `len(wave) == target_len` for every
processed waveform, to rule out a silent length-mismatch bug upstream of
the display layer.

**Fix direction (Phase 7 implementation):**
- Add length assertion/logging in `processor.py` to confirm pipeline
  correctness independent of the display.
- `CycleView` should display a sample-count label (e.g. "100 smp") so the
  user has a concrete reference matching the Length parameter.
- Consider drawing a fixed-amplitude zero line and gridlines so the user
  can visually judge periodicity and cleanliness of the cycle, similar to
  the grid treatment already used in `SpectrumView`.

---

## 11. Fixed Design Decisions

- **Stereo input:** left channel only. No channel selection, no mixing.
- **Filter order:** 2-pole (12 dB/oct) biquad, fixed. Not exposed.
- **Waveform style:** raw waveform = line; spectrum = filled silhouette.
- **Undo/redo:** not included.
- **Presets:** not included.
- **Export format:** plain numbered WAVs in a ZIP. No synth metadata.

---

## 12. Open Questions Resolved in Planning

| Question | Resolution |
|---|---|
| Zero-crossing interpolation method | Linear sub-sample interpolation |
| Central ZC uniqueness | No two regions may share the same center_zc |
| Pitch detection | Not needed — pitch inferred from ZC spacing |
| Time-stretch quality | pyrubberband (Rubber Band Library) |
| Filter scope | Applied to exports AND original-file preview playback |
| Modify parameter interpolation | begin = wave 0, end = wave N, linear across all |
| Offset behaviour | Window shifts around fixed center ZC |
| Stereo handling | Left channel only |
| Export format | Plain numbered WAVs in ZIP, no metadata |
| Filter cutoff definition | -3dB / half-power point, 2-pole = 12dB/oct rolloff beyond cutoff. Confirmed acceptable in Phase 7 review. |
| Filter cutoff definition | The -3dB (half-power) point; 2-pole = 12dB/oct rolloff beyond cutoff. Confirmed acceptable in Phase 7 review. |
