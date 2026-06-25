"""
ui/spectrum_view.py
Spectrum display widget.

Shows the FFT magnitude spectrum as a filled silhouette on a dark canvas,
log-frequency X axis (20 Hz - 22050 Hz), dB Y axis.

Interactive filter handle:
  - Left/right drag sets filter cutoff (log-frequency mapped)
  - Up/down drag sets filter Q (slow response: full widget height = 4 decades)
  - A vertical line shows current cutoff; a label shows Hz and Q values
  - Emits cutoff_changed(float) and q_changed(float) signals

Phase 1: spectrum silhouette only.
Phase 3: filter response overlay drawn here.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QRect, QRectF, QSize, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QLinearGradient,
    QMouseEvent, QCursor,
)
from PySide6.QtWidgets import QWidget, QSizePolicy

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
BG_COLOR        = QColor(0x12, 0x12, 0x18)
SPEC_FILL_TOP   = QColor(0x3A, 0x7B, 0xFF, 100)   # dimmed when filter active
SPEC_FILL_BOT   = QColor(0x1A, 0x3A, 0x88,  35)
SPEC_FILL_TOP_INACTIVE = QColor(0x3A, 0x7B, 0xFF, 180)   # full brightness when Off
SPEC_FILL_BOT_INACTIVE = QColor(0x1A, 0x3A, 0x88,  60)
SPEC_LINE       = QColor(0x5A, 0x9B, 0xFF, 220)
GRID_COLOR      = QColor(0x30, 0x30, 0x40)
GRID_TEXT_COLOR = QColor(0x55, 0x55, 0x70)
CUTOFF_LINE     = QColor(0xFF, 0xCC, 0x44, 200)   # amber cutoff marker
CUTOFF_LABEL    = QColor(0xFF, 0xCC, 0x44, 230)
FILTER_OVERLAY  = QColor(0xFF, 0xA0, 0x20, 110)   # amber, more opaque for contrast

FREQ_MIN = 20.0
FREQ_MAX = 22050.0
DB_MIN   = -90.0
DB_MAX   =   6.0

GRID_FREQS = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]

# Q drag sensitivity: pixels per decade of Q
# Full Q range 0.1-10 = 2 decades. We map so that ~300px = 2 decades,
# i.e. 150px per decade. This gives "reasonably slow" response.
_Q_PX_PER_DECADE = 150.0
_Q_MIN = 0.1
_Q_MAX = 10.0
_CUTOFF_HIT = 8   # px hit zone for cutoff line


class SpectrumView(QWidget):
    """Spectrum display widget with interactive filter handle.

    Signals
    -------
    cutoff_changed(float)  -- new cutoff in Hz
    q_changed(float)       -- new Q value
    """

    cutoff_changed = Signal(float)
    q_changed      = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(120)
        self.setMaximumHeight(170)
        self.setMouseTracking(True)

        # Spectrum data
        self._freqs: Optional[np.ndarray] = None
        self._db:    Optional[np.ndarray] = None

        # Filter state (kept internally; also pushed in from param panel)
        self._cutoff_hz: float = 8000.0
        self._q:         float = 0.707
        self._filter_mode: str = "LP"

        # Filter response for overlay (Phase 3)
        self._filter_resp_freqs: Optional[np.ndarray] = None
        self._filter_resp_db:    Optional[np.ndarray] = None

        # Drag state
        self._dragging: bool  = False
        self._drag_start_x: int = 0
        self._drag_start_y: int = 0
        self._drag_start_cutoff: float = 8000.0
        self._drag_start_q: float = 0.707

    # ------------------------------------------------------------------
    # Public setters
    # ------------------------------------------------------------------

    def set_samples(self, samples: Optional[np.ndarray], sr: int = 44100) -> None:
        if samples is None or len(samples) == 0:
            self._freqs = None
            self._db    = None
        else:
            self._freqs, self._db = _compute_spectrum(samples, sr)
        self.update()

    def set_filter_params(self, cutoff: float, q: float, mode: str) -> None:
        """Push filter params in from the param panel (keeps display in sync)."""
        self._cutoff_hz  = cutoff
        self._q          = q
        self._filter_mode = mode
        self.update()

    def set_filter_response(
        self,
        freqs: Optional[np.ndarray],
        db: Optional[np.ndarray],
    ) -> None:
        """Phase 3: pre-computed filter response for overlay."""
        self._filter_resp_freqs = freqs
        self._filter_resp_db    = db
        self.update()

    def clear(self) -> None:
        self._freqs = None
        self._db    = None
        self._filter_resp_freqs = None
        self._filter_resp_db    = None
        self.update()

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def sizeHint(self) -> QSize:
        return QSize(800, 140)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, BG_COLOR)
        self._draw_grid(p, w, h)

        if self._freqs is not None and self._db is not None:
            self._draw_spectrum(p, w, h)
            self._draw_filter_overlay(p, w, h)

        self._draw_cutoff_marker(p, w, h)

        if self._freqs is None:
            p.setPen(QColor(0x50, 0x50, 0x60))
            p.drawText(QRect(0, 0, w, h), Qt.AlignCenter, "no spectrum")

        p.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        if self._near_cutoff(event.position().x()):
            self._dragging = True
            self._drag_start_x      = int(event.position().x())
            self._drag_start_y      = int(event.position().y())
            self._drag_start_cutoff = self._cutoff_hz
            self._drag_start_q      = self._q
            self.setCursor(QCursor(Qt.SizeAllCursor))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        mx = event.position().x()
        my = event.position().y()

        if not self._dragging:
            if self._near_cutoff(mx):
                self.setCursor(QCursor(Qt.SizeAllCursor))
            else:
                self.setCursor(QCursor(Qt.ArrowCursor))
            return

        w = self.width()

        # --- Left/right: cutoff (log-frequency) ---
        dx = mx - self._drag_start_x
        log_min = math.log10(FREQ_MIN)
        log_max = math.log10(FREQ_MAX)
        log_range = log_max - log_min
        # 1 px = log_range / w decades
        log_start = math.log10(max(self._drag_start_cutoff, FREQ_MIN))
        new_log = log_start + dx * log_range / w
        new_cutoff = 10.0 ** new_log
        new_cutoff = max(FREQ_MIN, min(FREQ_MAX, new_cutoff))
        if abs(new_cutoff - self._cutoff_hz) > 0.1:
            self._cutoff_hz = new_cutoff
            self.cutoff_changed.emit(new_cutoff)

        # --- Up/down: Q (log scale, slow response) ---
        dy = my - self._drag_start_y   # positive = down = lower Q
        log_q_start = math.log10(max(self._drag_start_q, _Q_MIN))
        delta_decades = -dy / _Q_PX_PER_DECADE
        new_log_q = log_q_start + delta_decades
        new_q = 10.0 ** new_log_q
        new_q = max(_Q_MIN, min(_Q_MAX, new_q))
        if abs(new_q - self._q) > 0.001:
            self._q = new_q
            self.q_changed.emit(new_q)

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = False
        self.setCursor(QCursor(Qt.ArrowCursor))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_grid(self, p: QPainter, w: int, h: int) -> None:
        p.setPen(QPen(GRID_COLOR, 1))
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        for freq in GRID_FREQS:
            x = _freq_to_x(freq, w)
            p.setPen(GRID_COLOR)
            p.drawLine(int(x), 0, int(x), h)
            label = f"{freq // 1000}k" if freq >= 1000 else str(freq)
            p.setPen(GRID_TEXT_COLOR)
            p.drawText(int(x) + 2, h - 4, label)

    def _draw_spectrum(self, p: QPainter, w: int, h: int) -> None:
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
            return
        path.lineTo(_freq_to_x(self._freqs[-1], w), h)
        path.closeSubpath()

        # Dim the raw spectrum when filter is active so the overlay is readable
        filter_active = self._filter_mode != "OFF"
        top = SPEC_FILL_TOP if filter_active else SPEC_FILL_TOP_INACTIVE
        bot = SPEC_FILL_BOT if filter_active else SPEC_FILL_BOT_INACTIVE
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, top)
        grad.setColorAt(1.0, bot)
        p.fillPath(path, grad)
        p.setPen(QPen(SPEC_LINE, 1))
        p.drawPath(path)

    def _draw_filter_overlay(self, p: QPainter, w: int, h: int) -> None:
        """Draw filter frequency response overlay. Hidden when filter is Off."""
        if self._filter_mode == "OFF":
            return
        if self._filter_resp_freqs is None or self._filter_resp_db is None:
            return

        freqs = self._filter_resp_freqs
        db    = self._filter_resp_db

        path = QPainterPath()
        started = False
        last_x = 0.0
        for freq, d in zip(freqs, db):
            if freq < FREQ_MIN:
                continue
            x = _freq_to_x(freq, w)
            y = _db_to_y(d, h)
            y = max(0.0, min(float(h), y))
            if not started:
                path.moveTo(x, h)
                path.lineTo(x, y)
                started = True
            else:
                path.lineTo(x, y)
            last_x = x

        if not started:
            return

        path.lineTo(last_x, h)
        path.closeSubpath()

        p.fillPath(path, FILTER_OVERLAY)

        # Bold response curve line
        p.setPen(QPen(QColor(0xFF, 0xC0, 0x40, 220), 2))
        path2 = QPainterPath()
        started = False
        for freq, d in zip(freqs, db):
            if freq < FREQ_MIN:
                continue
            x = _freq_to_x(freq, w)
            y = _db_to_y(d, h)
            if not started:
                path2.moveTo(x, y)
                started = True
            else:
                path2.lineTo(x, y)
        p.drawPath(path2)

    def _draw_cutoff_marker(self, p: QPainter, w: int, h: int) -> None:
        """Draw the amber cutoff line + label with Q value. Hidden when filter is Off."""
        if self._filter_mode == "OFF":
            return

        x  = _freq_to_x(self._cutoff_hz, w)
        xi = int(x)

        # Dashed vertical line
        p.setPen(QPen(CUTOFF_LINE, 1, Qt.DashLine))
        p.drawLine(xi, 0, xi, h)

        # Label
        hz_str = f"{self._cutoff_hz:.0f} Hz" if self._cutoff_hz >= 100 else \
                 f"{self._cutoff_hz:.1f} Hz"
        label = f"{hz_str}  Q:{self._q:.2f}  {self._filter_mode}"
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        p.setPen(CUTOFF_LABEL)
        lx = xi + 4
        if lx + 130 > w:
            lx = xi - 134
        p.drawText(lx, 14, label)

        # Diamond handle at midpoint
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPolygon
        p.setBrush(CUTOFF_LINE)
        p.setPen(Qt.NoPen)
        d = 5
        diamond = QPolygon([
            QPoint(xi,     h // 2 - d),
            QPoint(xi + d, h // 2),
            QPoint(xi,     h // 2 + d),
            QPoint(xi - d, h // 2),
        ])
        p.drawPolygon(diamond)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _near_cutoff(self, px: float) -> bool:
        cx = _freq_to_x(self._cutoff_hz, self.width())
        return abs(px - cx) <= _CUTOFF_HIT


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _freq_to_x(freq: float, width: int) -> float:
    log_min = math.log10(FREQ_MIN)
    log_max = math.log10(FREQ_MAX)
    return (math.log10(max(freq, FREQ_MIN)) - log_min) / (log_max - log_min) * width


def _db_to_y(db: float, height: int) -> float:
    db = max(DB_MIN, min(DB_MAX, db))
    return height - (db - DB_MIN) / (DB_MAX - DB_MIN) * height


def _x_to_freq(x: float, width: int) -> float:
    log_min = math.log10(FREQ_MIN)
    log_max = math.log10(FREQ_MAX)
    log_f = log_min + (x / width) * (log_max - log_min)
    return 10.0 ** log_f


def _compute_spectrum(samples: np.ndarray, sr: int):
    from scipy.fft import rfft, rfftfreq
    n = len(samples)
    if n > 65536:
        start = (n - 65536) // 2
        chunk = samples[start: start + 65536]
    else:
        chunk = samples
    fft_n    = len(chunk)
    window   = np.hanning(fft_n)
    spectrum = rfft(chunk * window)
    freqs    = rfftfreq(fft_n, d=1.0 / sr)
    magnitude = np.abs(spectrum) / (fft_n / 2.0)
    magnitude = np.clip(magnitude, 1e-10, None)
    db = 20.0 * np.log10(magnitude)
    return freqs.astype(np.float64), db.astype(np.float64)
