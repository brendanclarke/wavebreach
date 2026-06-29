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
        self._lock   = threading.Lock()
        self._playing = False
        self._stream  = None   # holds OutputStream when looping

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return _SD_AVAILABLE

    def stop(self) -> None:
        """Stop any currently playing audio (one-shot or loop)."""
        if not _SD_AVAILABLE:
            return
        # Close loop stream if open
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.debug("stream close error: %s", exc)
            self._stream = None
        try:
            sd.stop()
        except Exception as exc:
            logger.debug("sounddevice stop error: %s", exc)
        with self._lock:
            self._playing = False

    def is_playing(self) -> bool:
        with self._lock:
            return self._playing
        """Play *samples* once. Stops any currently playing audio first."""
        if not _SD_AVAILABLE:
            logger.warning("play_array called but sounddevice is not available.")
            return

        self.stop()
        audio = samples.astype(np.float32)

        with self._lock:
            self._playing = True

        try:
            sd.play(audio, samplerate=sr)
            t = threading.Thread(target=self._wait_done, daemon=True)
            t.start()
        except Exception as exc:
            logger.error("sounddevice play error: %s", exc)
            with self._lock:
                self._playing = False

    def play_array(self, samples: np.ndarray, sr: int = 44100) -> None:
        """Play *samples* once at *sr*. Stops any current audio first."""
        if not _SD_AVAILABLE:
            logger.warning("play_array called but sounddevice is not available.")
            return
        self.stop()
        audio = samples.astype(np.float32)
        with self._lock:
            self._playing = True
        try:
            sd.play(audio, samplerate=sr)
            t = threading.Thread(target=self._wait_done, daemon=True)
            t.start()
        except Exception as exc:
            logger.error("sounddevice play error: %s", exc)
            with self._lock:
                self._playing = False

    def play_loop(self, samples: np.ndarray, sr: int = 44100) -> None:
        """Play *samples* in a continuous loop until stop() is called."""
        if not _SD_AVAILABLE:
            logger.warning("play_loop called but sounddevice is not available.")
            return

        self.stop()
        audio = samples.astype(np.float32)
        pos   = [0]   # mutable closure for callback position

        def _callback(outdata, frames, time_info, status):
            n = len(audio)
            chunk = np.empty(frames, dtype=np.float32)
            written = 0
            while written < frames:
                remaining_in_buf = n - pos[0]
                needed = frames - written
                take = min(remaining_in_buf, needed)
                chunk[written:written + take] = audio[pos[0]:pos[0] + take]
                written += take
                pos[0]  += take
                if pos[0] >= n:
                    pos[0] = 0   # wrap
            outdata[:, 0] = chunk

        with self._lock:
            self._playing = True

        try:
            self._stream = sd.OutputStream(
                samplerate=sr,
                channels=1,
                dtype=np.float32,
                callback=_callback,
            )
            self._stream.start()
        except Exception as exc:
            logger.error("sounddevice loop error: %s", exc)
            with self._lock:
                self._playing = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _wait_done(self) -> None:
        """Block until sounddevice one-shot finishes, then clear flag."""
        if not _SD_AVAILABLE:
            return
        try:
            sd.wait()
        except Exception:
            pass
        with self._lock:
            self._playing = False
