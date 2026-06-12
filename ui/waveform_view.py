"""
ui/waveform_view.py
Original-file waveform display widget.

Draws on a dark canvas:
  - Waveform as 1-px polyline (min/max per pixel column)
  - Zero line
  - Blue overlay on selected regions
  - Green/magenta overlays on excluded regions
  - White 1-px split lines at region ZC boundaries
  - Orange draggable Start marker (vertical line + handle triangle)
  - Cyan draggable End marker (vertical line + handle triangle)

Below the canvas, a row of two QSliders: Zoom and Position.
  Zoom:     1x to 50x (log scale) -- narrows the visible sample window
  Position: 0-100 -- scrolls within the zoomed window

Start/End markers are draggable directly on the canvas and also controlled
by spinboxes in ParamPanel via set_start_pad() / set_end_pad().
Dragging emits start_changed(int) / end_changed(int) signals.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QRect, QRectF, QSize, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPen, QResizeEvent, QMouseEvent,
    QCursor, QPolygon,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QSlider, QLabel,
)
from PySide6.QtCore import QPoint

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
BG_COLOR      = QColor(0x12, 0x12, 0x18)
WAVE_COLOR    = QColor(0x3A, 0x7B, 0xFF)
ZERO_COLOR    = QColor(0x40, 0x40, 0x50)
SPLIT_COLOR   = QColor(0xFF, 0xFF, 0xFF, 200)
SEL_OVERLAY   = QColor(0x64, 0xB4, 0xFF,  55)
MIN_OVERLAY   = QColor(0x64, 0xFF, 0x64,  45)
MAX_OVERLAY   = QColor(0xFF, 0x64, 0xFF,  45)
START_COLOR   = QColor(0xFF, 0x99, 0x22, 220)   # orange
END_COLOR     = QColor(0x22, 0xEE, 0xCC, 220)   # cyan
MARKER_HIT    = 8    # px either side counts as a hit for drag

# Zoom slider: steps map 1x to 50x on a log scale
_ZOOM_STEPS  = 1000
_ZOOM_MIN    = 1.0
_ZOOM_MAX    = 50.0

def _slider_to_zoom(v: int) -> float:
    t = v / _ZOOM_STEPS
    return _ZOOM_MIN * (_ZOOM_MAX / _ZOOM_MIN) ** t

def _zoom_to_slider(z: float) -> int:
    z = max(_ZOOM_MIN, min(_ZOOM_MAX, z))
    t = math.log(z / _ZOOM_MIN) / math.log(_ZOOM_MAX / _ZOOM_MIN)
    return int(t * _ZOOM_STEPS)


# ---------------------------------------------------------------------------
# Canvas widget (inner, no sliders)
# ---------------------------------------------------------------------------

class _WaveCanvas(QWidget):
    """The actual drawing surface. Handles mouse drag for Start/End markers."""

    start_dragged = Signal(int)   # new start_pad in samples
    end_dragged   = Signal(int)   # new end_pad in samples

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self._samples: Optional[np.ndarray] = None
        self._total_samples: int = 0

        # Viewport (set by zoom/position sliders)
        self._view_start: int = 0    # first sample visible
        self._view_end:   int = 0    # last sample visible (exclusive)

        # Overlay data
        self._selected_waves: list = []
        self._excluded_min:   list = []
        self._excluded_max:   list = []

        # Marker positions (in samples, absolute)
        self._start_pad: int = 0
        self._end_pad:   int = 0    # stored as samples-from-end

        # Drag state
        self._dragging: Optional[str] = None   # 'start' | 'end' | None
        self._drag_offset: int = 0

        # Pixel cache
        self._px_min: Optional[np.ndarray] = None
        self._px_max: Optional[np.ndarray] = None
        self._cached_width:  int = 0
        self._cached_v0:     int = -1
        self._cached_v1:     int = -1

    # ------------------------------------------------------------------
    # Public setters
    # ------------------------------------------------------------------

    def set_samples(self, samples: Optional[np.ndarray]) -> None:
        self._samples = samples
        self._total_samples = len(samples) if samples is not None else 0
        self._view_start = 0
        self._view_end   = self._total_samples
        self._invalidate_cache()
        self.update()

    def set_viewport(self, view_start: int, view_end: int) -> None:
        self._view_start = view_start
        self._view_end   = view_end
        self._invalidate_cache()
        self.update()

    def set_regions(self, selected, exc_min, exc_max) -> None:
        self._selected_waves = selected
        self._excluded_min   = exc_min
        self._excluded_max   = exc_max
        self.update()

    def set_markers(self, start_pad: int, end_pad: int) -> None:
        self._start_pad = start_pad
        self._end_pad   = end_pad
        self.update()

    def clear(self) -> None:
        self._samples = None
        self._total_samples = 0
        self._view_start = 0
        self._view_end   = 0
        self._selected_waves = []
        self._excluded_min   = []
        self._excluded_max   = []
        self._start_pad = 0
        self._end_pad   = 0
        self._invalidate_cache()
        self.update()

    # ------------------------------------------------------------------
    # Qt overrides
    # ------------------------------------------------------------------

    def sizeHint(self) -> QSize:
        return QSize(800, 180)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._invalidate_cache()
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, BG_COLOR)

        if self._samples is None or self._total_samples == 0:
            p.setPen(QPen(ZERO_COLOR, 1))
            p.drawLine(0, h // 2, w, h // 2)
            p.setPen(QColor(0x50, 0x50, 0x60))
            p.drawText(QRect(0, 0, w, h), Qt.AlignCenter, "no file loaded")
            p.end()
            return

        vs, ve = self._view_start, self._view_end
        if vs >= ve:
            p.end()
            return

        if self._px_min is None or self._cached_width != w \
                or self._cached_v0 != vs or self._cached_v1 != ve:
            self._build_cache(w, vs, ve)

        # Overlays
        p.setRenderHint(QPainter.Antialiasing, False)
        self._draw_excluded_overlays(p, w, h, vs, ve)
        self._draw_selected_overlays(p, w, h, vs, ve)

        # Zero line
        cy = h // 2
        p.setPen(QPen(ZERO_COLOR, 1))
        p.drawLine(0, cy, w, cy)

        # Waveform
        p.setRenderHint(QPainter.Antialiasing, True)
        self._draw_waveform(p, w, h)

        # Split lines
        self._draw_split_lines(p, w, h, vs, ve)

        # Start/End markers (on top of everything)
        p.setRenderHint(QPainter.Antialiasing, True)
        self._draw_marker(p, w, h, self._start_pad, START_COLOR, 'start')
        end_abs = self._total_samples - self._end_pad
        self._draw_marker(p, w, h, end_abs, END_COLOR, 'end')

        p.end()

    # ------------------------------------------------------------------
    # Mouse events for dragging markers
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        mx = event.position().x()
        if self._hit_marker(mx, self._start_pad):
            self._dragging = 'start'
            self.setCursor(QCursor(Qt.SizeHorCursor))
        elif self._hit_marker(mx, self._total_samples - self._end_pad):
            self._dragging = 'end'
            self.setCursor(QCursor(Qt.SizeHorCursor))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        mx = event.position().x()
        if self._dragging is None:
            # Cursor hint
            if (self._samples is not None and
                    (self._hit_marker(mx, self._start_pad) or
                     self._hit_marker(mx, self._total_samples - self._end_pad))):
                self.setCursor(QCursor(Qt.SizeHorCursor))
            else:
                self.setCursor(QCursor(Qt.ArrowCursor))
            return

        sample = self._x_to_sample(mx)
        if self._dragging == 'start':
            # start_pad = clamped sample position, must not exceed end marker
            end_abs = self._total_samples - self._end_pad
            new_val = max(0, min(sample, end_abs - 1))
            self._start_pad = new_val
            self.start_dragged.emit(new_val)
            self.update()
        elif self._dragging == 'end':
            # end_pad = total - sample position
            new_abs = max(self._start_pad + 1, min(sample, self._total_samples))
            new_pad = self._total_samples - new_abs
            self._end_pad = new_pad
            self.end_dragged.emit(new_pad)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._dragging = None
        self.setCursor(QCursor(Qt.ArrowCursor))

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_waveform(self, p: QPainter, w: int, h: int) -> None:
        if self._px_min is None or self._px_max is None:
            return
        cy  = h / 2.0
        amp = cy - 2
        pen = QPen(WAVE_COLOR, 1)
        pen.setCosmetic(True)
        p.setPen(pen)
        for x in range(w):
            y_top = cy - self._px_max[x] * amp
            y_bot = cy - self._px_min[x] * amp
            if abs(y_top - y_bot) < 1.0:
                p.drawPoint(x, int(y_top))
            else:
                p.drawLine(x, int(y_top), x, int(y_bot))

    def _draw_excluded_overlays(self, p, w, h, vs, ve):
        for (s, e) in self._excluded_min:
            x0 = self._sample_to_x(s, w, vs, ve)
            x1 = self._sample_to_x(e, w, vs, ve)
            if x1 > 0 and x0 < w:
                p.fillRect(QRectF(x0, 0, x1 - x0, h), MIN_OVERLAY)
        for (s, e) in self._excluded_max:
            x0 = self._sample_to_x(s, w, vs, ve)
            x1 = self._sample_to_x(e, w, vs, ve)
            if x1 > 0 and x0 < w:
                p.fillRect(QRectF(x0, 0, x1 - x0, h), MAX_OVERLAY)

    def _draw_selected_overlays(self, p, w, h, vs, ve):
        for region in self._selected_waves:
            x0 = self._sample_to_x(region.begin_zc, w, vs, ve)
            x1 = self._sample_to_x(region.end_zc,   w, vs, ve)
            if x1 > 0 and x0 < w:
                p.fillRect(QRectF(x0, 0, x1 - x0, h), SEL_OVERLAY)

    def _draw_split_lines(self, p, w, h, vs, ve):
        if not self._selected_waves:
            return
        pen = QPen(SPLIT_COLOR, 1)
        p.setPen(pen)
        seen: set[int] = set()
        for region in self._selected_waves:
            for zc in (region.begin_zc, region.end_zc):
                ix = int(self._sample_to_x(zc, w, vs, ve))
                if 0 <= ix < w and ix not in seen:
                    p.drawLine(ix, 0, ix, h)
                    seen.add(ix)

    def _draw_marker(self, p: QPainter, w: int, h: int,
                     sample_abs: int, color: QColor, which: str) -> None:
        """Draw a vertical marker line + small triangle handle at the top."""
        vs, ve = self._view_start, self._view_end
        if ve <= vs:
            return
        x = self._sample_to_x(float(sample_abs), w, vs, ve)
        xi = int(x)
        if xi < -2 or xi > w + 2:
            return

        pen = QPen(color, 1, Qt.SolidLine)
        p.setPen(pen)
        p.drawLine(xi, 0, xi, h)

        # Triangle handle at top, pointing down
        tri_w = 7
        tri_h = 10
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        pts = QPolygon([
            QPoint(xi - tri_w, 0),
            QPoint(xi + tri_w, 0),
            QPoint(xi, tri_h),
        ])
        p.drawPolygon(pts)

    # ------------------------------------------------------------------
    # Cache and coordinate helpers
    # ------------------------------------------------------------------

    def _build_cache(self, width: int, vs: int, ve: int) -> None:
        span = ve - vs
        if span <= 0 or width == 0:
            self._px_min = None
            self._px_max = None
            return
        px_min = np.empty(width, dtype=np.float64)
        px_max = np.empty(width, dtype=np.float64)
        for x in range(width):
            s0 = vs + int(x * span / width)
            s1 = vs + int((x + 1) * span / width)
            s1 = max(s1, s0 + 1)
            s0 = min(s0, len(self._samples) - 1)
            s1 = min(s1, len(self._samples))
            chunk = self._samples[s0:s1]
            px_min[x] = chunk.min()
            px_max[x] = chunk.max()
        self._px_min = px_min
        self._px_max = px_max
        self._cached_width = width
        self._cached_v0    = vs
        self._cached_v1    = ve

    def _invalidate_cache(self) -> None:
        self._px_min = None
        self._px_max = None
        self._cached_width = 0
        self._cached_v0    = -1
        self._cached_v1    = -1

    def _sample_to_x(self, sample: float, w: int, vs: int, ve: int) -> float:
        span = ve - vs
        if span <= 0:
            return 0.0
        return (sample - vs) / span * w

    def _x_to_sample(self, x: float) -> int:
        vs, ve = self._view_start, self._view_end
        span = ve - vs
        if span <= 0 or self.width() == 0:
            return vs
        return int(vs + x / self.width() * span)

    def _hit_marker(self, px: float, sample_abs: int) -> bool:
        vs, ve = self._view_start, self._view_end
        if ve <= vs:
            return False
        mx = self._sample_to_x(float(sample_abs), self.width(), vs, ve)
        return abs(px - mx) <= MARKER_HIT


# ---------------------------------------------------------------------------
# Public composite widget: canvas + zoom/position sliders
# ---------------------------------------------------------------------------

class WaveformView(QWidget):
    """
    Full waveform display: canvas + zoom slider + position slider.

    Signals
    -------
    start_changed(int)  -- user dragged start marker; value = new start_pad
    end_changed(int)    -- user dragged end marker; value = new end_pad
    """

    start_changed = Signal(int)
    end_changed   = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_samples = 0
        self._zoom = 1.0        # current zoom factor
        self._pos  = 0.0        # scroll position 0.0-1.0

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(2)

        # Canvas
        self._canvas = _WaveCanvas()
        self._canvas.setMinimumHeight(160)
        self._canvas.setMaximumHeight(220)
        self._canvas.start_dragged.connect(self._on_start_dragged)
        self._canvas.end_dragged.connect(self._on_end_dragged)
        vbox.addWidget(self._canvas)

        # Slider row
        slider_row = QHBoxLayout()
        slider_row.setContentsMargins(4, 0, 4, 2)
        slider_row.setSpacing(8)

        self._zoom_label = QLabel("Zoom")
        self._zoom_label.setProperty("dim", True)
        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setRange(0, _ZOOM_STEPS)
        self._zoom_slider.setValue(0)
        self._zoom_slider.setToolTip("Zoom waveform display (1x - 50x)")
        self._zoom_value_label = QLabel("1.0x")
        self._zoom_value_label.setFixedWidth(36)

        self._pos_label = QLabel("Pos")
        self._pos_label.setProperty("dim", True)
        self._pos_slider = QSlider(Qt.Horizontal)
        self._pos_slider.setRange(0, 1000)
        self._pos_slider.setValue(0)
        self._pos_slider.setEnabled(False)
        self._pos_slider.setToolTip("Scroll position within zoomed view")

        slider_row.addWidget(self._zoom_label)
        slider_row.addWidget(self._zoom_slider, 2)
        slider_row.addWidget(self._zoom_value_label)
        slider_row.addSpacing(12)
        slider_row.addWidget(self._pos_label)
        slider_row.addWidget(self._pos_slider, 3)

        vbox.addLayout(slider_row)

        self._zoom_slider.valueChanged.connect(self._on_zoom_changed)
        self._pos_slider.valueChanged.connect(self._on_pos_changed)

    # ------------------------------------------------------------------
    # Public API (mirrors old WaveformView for drop-in compatibility)
    # ------------------------------------------------------------------

    def set_samples(self, samples: Optional[np.ndarray]) -> None:
        self._total_samples = len(samples) if samples is not None else 0
        self._zoom = 1.0
        self._pos  = 0.0
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(0)
        self._zoom_slider.blockSignals(False)
        self._pos_slider.blockSignals(True)
        self._pos_slider.setValue(0)
        self._pos_slider.blockSignals(False)
        self._pos_slider.setEnabled(False)
        self._zoom_value_label.setText("1.0x")
        self._canvas.set_samples(samples)
        self._update_viewport()

    def set_regions(self, selected, exc_min, exc_max) -> None:
        self._canvas.set_regions(selected, exc_min, exc_max)

    def set_markers(self, start_pad: int, end_pad: int) -> None:
        self._canvas.set_markers(start_pad, end_pad)

    def clear(self) -> None:
        self._total_samples = 0
        self._zoom = 1.0
        self._pos  = 0.0
        self._canvas.clear()

    # ------------------------------------------------------------------
    # Slider handlers
    # ------------------------------------------------------------------

    def _on_zoom_changed(self, v: int) -> None:
        self._zoom = _slider_to_zoom(v)
        self._zoom_value_label.setText(f"{self._zoom:.1f}x")
        self._pos_slider.setEnabled(self._zoom > 1.0)
        self._update_viewport()

    def _on_pos_changed(self, v: int) -> None:
        self._pos = v / 1000.0
        self._update_viewport()

    def _update_viewport(self) -> None:
        n = self._total_samples
        if n == 0:
            return
        window = max(1, int(n / self._zoom))
        max_start = n - window
        view_start = int(self._pos * max_start)
        view_start = max(0, min(view_start, max_start))
        view_end   = view_start + window
        self._canvas.set_viewport(view_start, view_end)

    # ------------------------------------------------------------------
    # Marker drag callbacks -- forward to exterior
    # ------------------------------------------------------------------

    def _on_start_dragged(self, val: int) -> None:
        self.start_changed.emit(val)

    def _on_end_dragged(self, val: int) -> None:
        self.end_changed.emit(val)
