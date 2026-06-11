"""
core/playback.py
Thin wrapper around sounddevice for non-blocking audio playback.

PlaybackController is instantiated once in MainWindow and shared.
It supports:
  - play_array(samples, sr)          — one-shot playback of any float64 array
  - stop()
  - is_playing()                     — True while audio is running

Phase 1 uses this for the raw original-file preview (no filter yet —
filter support will be wired in Phase 3).  The filter is applied offline
(full array pre-processed) before passing to play_array(), so there is no
streaming complexity here.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except Exception as e:
    logger.warning("sounddevice not available: %s", e)
    _SD_AVAILABLE = False


class PlaybackController:
    """Simple non-blocking playback using sounddevice.

    All public methods are thread-safe (called from the Qt main thread).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._playing = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return _SD_AVAILABLE

    def play_array(self, samples: np.ndarray, sr: int = 44100) -> None:
        """Play *samples* (float64 mono or stereo) at sample rate *sr*.

        Stops any currently playing audio first.
        Does nothing if sounddevice is unavailable.
        """
        if not _SD_AVAILABLE:
            logger.warning("play_array called but sounddevice is not available.")
            return

        self.stop()

        # Ensure float32 for sounddevice (it accepts float64 too but float32
        # is the safer cross-platform choice)
        audio = samples.astype(np.float32)

        with self._lock:
            self._playing = True

        def _finished_callback():
            with self._lock:
                self._playing = False

        try:
            sd.play(audio, samplerate=sr)
            # Register a thread that waits for completion and clears the flag
            t = threading.Thread(target=self._wait_done, daemon=True)
            t.start()
        except Exception as exc:
            logger.error("sounddevice play error: %s", exc)
            with self._lock:
                self._playing = False

    def stop(self) -> None:
        """Stop any currently playing audio."""
        if not _SD_AVAILABLE:
            return
        try:
            sd.stop()
        except Exception as exc:
            logger.debug("sounddevice stop error: %s", exc)
        with self._lock:
            self._playing = False

    def is_playing(self) -> bool:
        with self._lock:
            return self._playing

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _wait_done(self) -> None:
        """Block until sounddevice finishes, then clear the playing flag."""
        if not _SD_AVAILABLE:
            return
        try:
            sd.wait()
        except Exception:
            pass
        with self._lock:
            self._playing = False
