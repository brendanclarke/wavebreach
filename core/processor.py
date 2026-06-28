"""
core/processor.py
Tier-2 (Go button) DSP pipeline orchestrator.

Runs in a background QThread.  Emits progress and completion signals.
Pipeline per waveform:
  1. Offset  (window shift)
  2. Stretch (asymmetric half-compress/expand via Rubber Band -- Modify only)
  3. Length normalisation: resample to target sample count via numpy.interp
     This is simple linear interpolation through the waveform shape --
     correct for single-cycle wavetable content where pitch is a property
     of playback rate, not of the stored samples.
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
from core import modifier, filter_dsp

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

        # --- Filter design (None when OFF) ---
        if s.filter_mode == "OFF":
            sos = None
        else:
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

            # Length normalisation: resample to target_len via interpolation.
            # numpy.interp maps target_len evenly-spaced points through the
            # source waveform shape -- correct and artifact-free for
            # single-cycle periodic material regardless of length ratio.
            if len(chunk) != target_len:
                x_old = np.linspace(0.0, 1.0, len(chunk))
                x_new = np.linspace(0.0, 1.0, target_len)
                wave  = np.interp(x_new, x_old, chunk)
            else:
                wave = chunk.astype(np.float64)

            # Filter (skip if OFF)
            if sos is not None:
                wave = filter_dsp.apply_filter(wave, sos)

            # Peak normalise
            if norm_peak is not None:
                peak = np.max(np.abs(wave))
                if peak > 1e-9:
                    wave = wave * (norm_peak / peak)

            # Hard clip to [-1, 1] for safety
            wave = np.clip(wave, -1.0, 1.0)

            # Verify length matches target (catches pipeline bugs)
            if len(wave) != target_len:
                logger.warning(
                    "Wave %d length mismatch: expected %d, got %d. Zero-padding.",
                    k, target_len, len(wave)
                )
                if len(wave) < target_len:
                    wave = np.concatenate([wave, np.zeros(target_len - len(wave))])
                else:
                    wave = wave[:target_len]

            processed.append(wave.astype(np.float64))

        logger.info("Processed %d waveforms, target length %d samples.", K, target_len)
        return processed
