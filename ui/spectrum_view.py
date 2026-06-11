"""
ui/spectrum_view.py
Spectrum display widget.

Shows the FFT magnitude spectrum of the loaded file as a filled silhouette
on a dark canvas, log-frequency X axis (20 Hz – 22050 Hz), dB Y axis.

Phase 1: spectrum silhouette only.
Filter overlay will be wired in Phase 3.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QRect, QPointF, QSize
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QLinearGradient, QResizeEvent,
)
from PySide6.QtWidgets import QWidget, QSizePolicy

# Canvas colours (same dark palette as WaveformView)
BG_COLOR        = QColor(0x12, 0x12, 0x18)
SPEC_FILL_TOP   = QColor(0x3A, 0x7B, 0xFF, 180)
SPEC_FILL_BOT   = QColor(0x1A, 0x3A, 0x88,  60)
SPEC_LINE       = QColor(0x5A, 0x9B, 0xFF, 220)
GRID_COLOR      = QColor(0x30, 0x30, 0x40)
GRID_TEXT_COLOR = QColor(0x55, 0x55, 0x70)
FILTER_OVERLAY  = QColor(0x64, 0xB4, 0xFF,  55)    # Phase 3

FREQ_MIN = 20.0
FREQ_MAX = 22050.0
DB_MIN   = -90.0
DB_MAX   =   6.0

# Frequency grid lines
GRID_FREQS = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]


class SpectrumView(QWidget):
    """Spectrum display widget using log-frequency axis."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(120)
        self.setMaximumHeight(170)

        # Computed spectrum data
        self._freqs: Optional[np.ndarray] = None    # Hz values
        self._db:    Optional[np.ndarray] = None    # dB magnitude

        # Filter response (Phase 3)
        self._filter_freqs: Optional[np.ndarray] = None
        self._filter_db:    Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Public setters
    # ------------------------------------------------------------------

    def set_samples(self, samples: Optional[np.ndarray], sr: int = 44100) -> None:
        """Compute FFT from *samples* (float64 mono) and repaint."""
        if samples is None or len(samples) == 0:
            self._freqs = None
            self._db    = None
            self.update()
            return

        self._freqs, self._db = _compute_spectrum(samples, sr)
        self.update()

    def set_filter_response(
        self,
        freqs: Optional[np.ndarray],
        db: Optional[np.ndarray],
    ) -> None:
        """Set pre-computed filter frequency response for overlay (Phase 3)."""
        self._filter_freqs = freqs
        self._filter_db    = db
        self.update()

    def clear(self) -> None:
        self._freqs = None
        self._db    = None
        self._filter_freqs = None
        self._filter_db    = None
        self.update()

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def sizeHint(self) -> QSize:
        return QSize(800, 140)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()

        p.fillRect(0, 0, w, h, BG_COLOR)
        self._draw_grid(p, w, h)

        if self._freqs is not None and self._db is not None:
            self._draw_spectrum(p, w, h)
            self._draw_filter_overlay(p, w, h)
        else:
            self._draw_placeholder(p, w, h)

        p.end()

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_placeholder(self, p: QPainter, w: int, h: int) -> None:
        p.setPen(QColor(0x50, 0x50, 0x60))
        p.drawText(QRect(0, 0, w, h), Qt.AlignCenter, "no spectrum")

    def _draw_grid(self, p: QPainter, w: int, h: int) -> None:
        pen = QPen(GRID_COLOR, 1, Qt.SolidLine)
        p.setPen(pen)
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        p.setPen(GRID_COLOR)

        for freq in GRID_FREQS:
            if freq < FREQ_MIN or freq > FREQ_MAX:
                continue
            x = _freq_to_x(freq, w)
            p.drawLine(int(x), 0, int(x), h)
            label = f"{freq // 1000}k" if freq >= 1000 else str(freq)
            p.setPen(GRID_TEXT_COLOR)
            p.drawText(int(x) + 2, h - 4, label)
            p.setPen(GRID_COLOR)

    def _draw_spectrum(self, p: QPainter, w: int, h: int) -> None:
        # Build screen-resolution point list from (freqs, db)
        path = QPainterPath()
        first = True
        for freq, db in zip(self._freqs, self._db):
            if freq < FREQ_MIN:
                continue
            x = _freq_to_x(freq, w)
            y = _db_to_y(db, h)
            if first:
                path.moveTo(x, h)
                path.lineTo(x, y)
                first = False
            else:
                path.lineTo(x, y)

        if first:
            return   # nothing drawn

        # Close path along bottom
        path.lineTo(_freq_to_x(self._freqs[-1], w), h)
        path.closeSubpath()

        # Gradient fill
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, SPEC_FILL_TOP)
        grad.setColorAt(1.0, SPEC_FILL_BOT)
        p.fillPath(path, grad)

        # Outline
        p.setPen(QPen(SPEC_LINE, 1))
        p.drawPath(path)

    def _draw_filter_overlay(self, p: QPainter, w: int, h: int) -> None:
        """Phase 3: draw filter response overlay.  Stub for now."""
        if self._filter_freqs is None or self._filter_db is None:
            return
        # TODO Phase 3: draw semi-transparent filled polygon
        pass


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _freq_to_x(freq: float, width: int) -> float:
    """Log-frequency to pixel X coordinate."""
    log_min = math.log10(FREQ_MIN)
    log_max = math.log10(FREQ_MAX)
    return (math.log10(max(freq, FREQ_MIN)) - log_min) / (log_max - log_min) * width


def _db_to_y(db: float, height: int) -> float:
    """dB value to pixel Y coordinate (0 dB at top, DB_MIN at bottom)."""
    db = max(DB_MIN, min(DB_MAX, db))
    return height - (db - DB_MIN) / (DB_MAX - DB_MIN) * height


def _compute_spectrum(samples: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (freqs_hz, magnitude_db) arrays for spectrum display.

    Uses a Hann-windowed FFT on the full sample array (or first 4096
    samples for very short files).  Returns only the positive frequency
    half (rfft).
    """
    from scipy.fft import rfft, rfftfreq

    n = len(samples)
    # For long files, use up to 65536 samples from the middle for a
    # representative snapshot.  The full waveform view handles time-domain.
    if n > 65536:
        start = (n - 65536) // 2
        chunk = samples[start : start + 65536]
    else:
        chunk = samples

    fft_n = len(chunk)
    window = np.hanning(fft_n)
    windowed = chunk * window

    spectrum = rfft(windowed)
    freqs    = rfftfreq(fft_n, d=1.0 / sr)

    magnitude = np.abs(spectrum) / (fft_n / 2.0)
    magnitude = np.clip(magnitude, 1e-10, None)
    db = 20.0 * np.log10(magnitude)

    return freqs.astype(np.float64), db.astype(np.float64)
