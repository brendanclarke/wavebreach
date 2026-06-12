"""
core/processor.py
Tier-2 (Go button) DSP pipeline orchestrator.

Runs in a background QThread.  Emits progress and completion signals.
Pipeline per waveform:
  1. Offset  (window shift)
  2. Stretch (asymmetric half-compress/expand)
  3. Length normalisation stretch (to target sample count)
  4. Filter  (biquad sosfilt)
  5. Normalise (peak scale)

Public usage (from MainWindow):
    worker = ProcessWorker(state)
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.progress.connect(update_progress_dialog)
    worker.finished.connect(on_done)
    worker.error.connect(on_error)
    thread.start()
"""

from __future__ import annotations

import logging
import numpy as np

from PySide6.QtCore import QObject, Signal

from core.state import AppState
from core import modifier, stretcher, filter_dsp

logger = logging.getLogger(__name__)


class ProcessWorker(QObject):
    """Runs the full DSP pipeline for all selected waveforms.

    Signals
    -------
    progress(int, int)  -- (current, total) for progress bar
    finished(list)      -- list[np.ndarray] of processed waveforms
    error(str)          -- human-readable error message
    """

    progress = Signal(int, int)
    finished = Signal(object)   # list[np.ndarray]
    error    = Signal(str)

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

    def run(self) -> None:
        try:
            result = self._process()
            self.finished.emit(result)
        except Exception as exc:
            logger.exception("DSP pipeline error")
            self.error.emit(str(exc))

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _process(self) -> list[np.ndarray]:
        s = self._state
        regions = s.selected_waves

        if not regions:
            logger.warning("No regions to process.")
            return []

        raw = s.raw_samples
        sr  = s.sample_rate
        K   = len(regions)

        # --- Target length ---
        if s.length_mode == "pitch":
            target_len = max(1, int(round(sr / max(s.length_hz, 0.1))))
        else:
            target_len = max(1, int(s.length_samples))

        # --- Filter design ---
        sos = filter_dsp.design_filter(s.filter_mode, s.filter_cutoff, s.filter_q, sr)

        # --- Normalise target ---
        if s.normalize_enabled:
            norm_peak = 10.0 ** (s.normalize_db / 20.0)
        else:
            norm_peak = None

        # --- Per-waveform Modify (offset + stretch + suppress) ---
        self.progress.emit(0, K)
        modified = modifier.apply_all(
            raw, regions,
            s.offset_begin,   s.offset_end,
            s.stretch_begin,  s.stretch_end,
            s.suppress_begin, s.suppress_end,
            sr,
        )

        # --- Length normalise + filter + normalize per waveform ---
        processed: list[np.ndarray] = []
        for k, chunk in enumerate(modified):
            self.progress.emit(k + 1, K)

            # Length normalise
            wave = stretcher.stretch_to_length(chunk, target_len, sr)

            # Filter
            wave = filter_dsp.apply_filter(wave, sos)

            # Peak normalise
            if norm_peak is not None:
                peak = np.max(np.abs(wave))
                if peak > 1e-9:
                    wave = wave * (norm_peak / peak)

            # Hard clip to [-1, 1] for safety
            wave = np.clip(wave, -1.0, 1.0)

            processed.append(wave.astype(np.float64))

        logger.info("Processed %d waveforms, target length %d samples.", K, target_len)
        return processed
