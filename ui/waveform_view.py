"""
ui/waveform_view.py
Original-file waveform display widget.

Draws:
  - Dark canvas background (always dark regardless of app theme)
  - Waveform as a 1-px anti-aliased polyline (one point per pixel column,
    using min/max downsampling for accurate peak representation)
  - Zero line
  - Vertical split lines for begin_zc / end_zc of selected waves (white)
  - Blue semi-transparent overlay between split lines (selected regions)
  - Green overlay for min-excluded regions
  - Magenta overlay for max-excluded regions

Phase 1: waveform + zero line only.
Overlays and split lines are stubbed and will be populated in Phase 2.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QRect, QRectF, QSize
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QResizeEvent,
)
from PySide6.QtWidgets import QWidget, QSizePolicy

# Canvas colour constants
BG_COLOR      = QColor(0x12, 0x12, 0x18)          # near-black blue-grey
WAVE_COLOR    = QColor(0x3A, 0x7B, 0xFF)           # accent blue
ZERO_COLOR    = QColor(0x40, 0x40, 0x50)           # dim line
SPLIT_COLOR   = QColor(0xFF, 0xFF, 0xFF, 200)      # white, slightly transparent
SEL_OVERLAY   = QColor(0x64, 0xB4, 0xFF,  55)      # light blue
MIN_OVERLAY   = QColor(0x64, 0xFF, 0x64,  45)      # light green
MAX_OVERLAY   = QColor(0xFF, 0x64, 0xFF,  45)      # light magenta


class WaveformView(QWidget):
    """Display widget for the raw loaded waveform.

    Set samples via set_samples().  Set overlay data via set_regions()
    (Phase 2).  The widget repaints automatically on resize.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(160)
        self.setMaximumHeight(220)

        # Data
        self._samples: Optional[np.ndarray] = None   # float64 mono
        self._total_samples: int = 0

        # Overlay data (Phase 2)
        self._selected_waves: list = []    # list[WaveRegion]
        self._excluded_min: list = []      # list[tuple[float,float]]
        self._excluded_max: list = []      # list[tuple[float,float]]

        # Pre-computed pixel columns cache
        self._px_min: Optional[np.ndarray] = None
        self._px_max: Optional[np.ndarray] = None
        self._cached_width: int = 0

    # ------------------------------------------------------------------
    # Public setters
    # ------------------------------------------------------------------

    def set_samples(self, samples: Optional[np.ndarray]) -> None:
        """Update the waveform data and repaint."""
        self._samples = samples
        self._total_samples = len(samples) if samples is not None else 0
        self._invalidate_cache()
        self.update()

    def set_regions(
        self,
        selected_waves: list,
        excluded_min: list,
        excluded_max: list,
    ) -> None:
        """Update overlay regions and repaint (called from Phase 2 live update)."""
        self._selected_waves = selected_waves
        self._excluded_min   = excluded_min
        self._excluded_max   = excluded_max
        self.update()

    def clear(self) -> None:
        self._samples = None
        self._total_samples = 0
        self._selected_waves = []
        self._excluded_min   = []
        self._excluded_max   = []
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
        p.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()
        h = self.height()

        # Background
        p.fillRect(0, 0, w, h, BG_COLOR)

        if self._samples is None or self._total_samples == 0:
            self._draw_placeholder(p, w, h)
            p.end()
            return

        # Ensure pixel column cache is valid
        if self._px_min is None or self._cached_width != w:
            self._build_cache(w)

        # ---- Overlays (bottom layer) ----
        p.setRenderHint(QPainter.Antialiasing, False)
        self._draw_excluded_overlays(p, w, h)
        self._draw_selected_overlays(p, w, h)

        # ---- Zero line ----
        cy = h // 2
        p.setPen(QPen(ZERO_COLOR, 1, Qt.SolidLine))
        p.drawLine(0, cy, w, cy)

        # ---- Waveform ----
        p.setRenderHint(QPainter.Antialiasing, True)
        self._draw_waveform(p, w, h)

        # ---- Split lines (top layer) ----
        self._draw_split_lines(p, w, h)

        p.end()

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_placeholder(self, p: QPainter, w: int, h: int) -> None:
        """Draw a dim 'no file loaded' indicator."""
        p.setPen(QPen(ZERO_COLOR, 1))
        p.drawLine(0, h // 2, w, h // 2)
        p.setPen(QColor(0x50, 0x50, 0x60))
        p.drawText(
            QRect(0, 0, w, h),
            Qt.AlignCenter,
            "no file loaded",
        )

    def _draw_waveform(self, p: QPainter, w: int, h: int) -> None:
        """Draw the waveform as a 1-px polyline using min/max per column."""
        if self._px_min is None or self._px_max is None:
            return

        cy = h / 2.0
        amp = cy - 2          # leave 2px margin top/bottom

        pen = QPen(WAVE_COLOR, 1, Qt.SolidLine)
        pen.setCosmetic(True)
        p.setPen(pen)

        # Draw a vertical line segment per pixel column (min→max)
        # This correctly represents transients and avoids aliasing.
        for x in range(w):
            y_top = cy - self._px_max[x] * amp
            y_bot = cy - self._px_min[x] * amp
            if abs(y_top - y_bot) < 1.0:
                p.drawPoint(x, int(y_top))
            else:
                p.drawLine(x, int(y_top), x, int(y_bot))

    def _draw_excluded_overlays(self, p: QPainter, w: int, h: int) -> None:
        if not (self._excluded_min or self._excluded_max):
            return

        for (s, e) in self._excluded_min:
            x0 = self._sample_to_x(s, w)
            x1 = self._sample_to_x(e, w)
            p.fillRect(QRectF(x0, 0, x1 - x0, h), MIN_OVERLAY)

        for (s, e) in self._excluded_max:
            x0 = self._sample_to_x(s, w)
            x1 = self._sample_to_x(e, w)
            p.fillRect(QRectF(x0, 0, x1 - x0, h), MAX_OVERLAY)

    def _draw_selected_overlays(self, p: QPainter, w: int, h: int) -> None:
        if not self._selected_waves:
            return
        for region in self._selected_waves:
            x0 = self._sample_to_x(region.begin_zc, w)
            x1 = self._sample_to_x(region.end_zc,   w)
            p.fillRect(QRectF(x0, 0, x1 - x0, h), SEL_OVERLAY)

    def _draw_split_lines(self, p: QPainter, w: int, h: int) -> None:
        if not self._selected_waves:
            return
        pen = QPen(SPLIT_COLOR, 1, Qt.SolidLine)
        p.setPen(pen)
        seen: set[int] = set()
        for region in self._selected_waves:
            for zc in (region.begin_zc, region.end_zc):
                ix = int(self._sample_to_x(zc, w))
                if ix not in seen:
                    p.drawLine(ix, 0, ix, h)
                    seen.add(ix)

    # ------------------------------------------------------------------
    # Cache / coordinate helpers
    # ------------------------------------------------------------------

    def _build_cache(self, width: int) -> None:
        """Pre-compute per-pixel-column min and max sample values."""
        n = self._total_samples
        if n == 0 or width == 0:
            self._px_min = None
            self._px_max = None
            return

        px_min = np.empty(width, dtype=np.float64)
        px_max = np.empty(width, dtype=np.float64)

        # Map each pixel column to a sample range
        for x in range(width):
            s0 = int(x * n / width)
            s1 = int((x + 1) * n / width)
            s1 = max(s1, s0 + 1)
            chunk = self._samples[s0:s1]
            px_min[x] = chunk.min()
            px_max[x] = chunk.max()

        self._px_min = px_min
        self._px_max = px_max
        self._cached_width = width

    def _invalidate_cache(self) -> None:
        self._px_min = None
        self._px_max = None
        self._cached_width = 0

    def _sample_to_x(self, sample_pos: float, width: int) -> float:
        """Convert a sample index to a pixel X coordinate."""
        if self._total_samples == 0:
            return 0.0
        return sample_pos / self._total_samples * width
