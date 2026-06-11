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
