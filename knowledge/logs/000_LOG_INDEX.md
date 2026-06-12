# 000_LOG_INDEX.md
## Wavebreach — Session Log Index

Each entry links to a session log and summarises what was done.
Cross-references point to relevant sections of PLANNING.md and CLAUDE.md.

---

| Log | Date | Phase | Summary |
|---|---|---|---|
| [001](001_SESSION_LOG.md) | 2026-06-10 | Phase 1 | Initial planning, spec clarification, full Phase 1 implementation: project skeleton, audio I/O, waveform display, spectrum display, parameter panel, playback panel, raw audio playback |
| [002](002_SESSION_LOG.md) | 2026-06-10 | Phase 2 | ZC detection, splitter, live waveform overlays |

---

## Knowledge Cross-Reference

| Topic | Where defined | First used |
|---|---|---|
| AppState / WaveRegion dataclasses | CLAUDE.md §Architecture, PLANNING.md §6 | Session 001 |
| Two-tier update model | CLAUDE.md §Architecture | Session 001 |
| Zero-crossing interpolation formula | PLANNING.md §6 | Session 002 |
| Min/max exclusion zone logic | PLANNING.md §6 | Session 002 |
| WaveRegion selection algorithm | PLANNING.md §6 | Session 002 |
| Center ZC uniqueness guarantee | PLANNING.md §6, CLAUDE.md §ZC Model | Session 002 |
| Offset parameter behaviour | PLANNING.md §5 Modify, CLAUDE.md §Offset | Session 001 (clarified) |
| Modify interpolation formula | PLANNING.md §5 Modify | Session 001 (clarified) |
| DSP pipeline order | PLANNING.md §7 | Session 003 (Phase 3) |
| Filter SVF biquad formulation | PLANNING.md §9 | Session 003 (Phase 3) |
| pyrubberband stretch wrapper | PLANNING.md §9 | Session 003 (Phase 3) |
| [004](004_SESSION_LOG.md) | 2026-06-12 | Phase 3+4 | Full DSP pipeline: filter_dsp, stretcher, modifier, processor (QThread), filtered playback, spectrum overlay, slider layout fix |
| [003](003_SESSION_LOG.md) | 2026-06-10 | Phase 2b | Draggable UI elements: waveform zoom/position sliders, draggable Start/End markers on waveform canvas, draggable cutoff (L/R) and Q (U/D) on spectrum canvas, log-scale sliders for cutoff and Q in param panel, all controls bidirectionally wired |

---

## Knowledge Cross-Reference (additions from Session 003)

| Topic | Where defined | First used |
|---|---|---|
| Waveform zoom/pos slider log scale | `ui/waveform_view.py` `_slider_to_zoom` / `_zoom_to_slider` | Session 003 |
| Start/End marker drag on canvas | `ui/waveform_view.py` `_WaveCanvas` mouse events | Session 003 |
| Spectrum cutoff drag (L/R log-freq) | `ui/spectrum_view.py` `mouseMoveEvent` | Session 003 |
| Spectrum Q drag (U/D log-scale, 150px/decade) | `ui/spectrum_view.py` `mouseMoveEvent` | Session 003 |
| Cutoff/Q log-scale sliders | `ui/param_panel.py` `_cutoff_to_slider` etc. | Session 003 |
| Bidirectional spin↔slider wiring (blockSignals) | `ui/param_panel.py` `_on_*_changed` handlers | Session 003 |
| spec_view.set_filter_params() sync | `ui/main_window.py` `_on_params_changed` | Session 003 |
