"""
ui/playback_panel.py
Right-side preview and export panel.

Phase 1:
  - Single-cycle waveform canvas (shows placeholder)
  - Prev / Next buttons (disabled until Go)
  - Play All / Loop / Speed controls (disabled until Go)
  - Wavetable name field
  - Export ZIP button (disabled until Go)

Full wiring to processed_waves and PlaybackController happens in Phase 5.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFontMetrics,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QSlider, QLineEdit, QGroupBox, QSizePolicy, QFrame,
)

from core.state import AppState


# ---------------------------------------------------------------------------
# Mini waveform canvas for single-cycle preview
# ---------------------------------------------------------------------------

class CycleView(QWidget):
    """Displays a single processed single-cycle waveform.

    Shows:
      - Dark canvas with zero line and quarter-cycle grid
      - Waveform as 1-px polyline (green)
      - Sample count label (bottom-right) confirming length
    """

    BG      = QColor(0x12, 0x12, 0x18)
    LINE    = QColor(0x3A, 0xC8, 0x7B)
    ZERO    = QColor(0x40, 0x40, 0x50)
    GRID    = QColor(0x28, 0x28, 0x38)
    LABEL_C = QColor(0x44, 0x66, 0x44)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(140)
        self.setMaximumHeight(180)
        self._samples: Optional[np.ndarray] = None

    def set_samples(self, samples: Optional[np.ndarray]) -> None:
        self._samples = samples
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(400, 160)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, self.BG)

        cy = h // 2

        # Quarter-cycle vertical grid lines
        p.setPen(QPen(self.GRID, 1))
        for frac in (0.25, 0.5, 0.75):
            gx = int(w * frac)
            p.drawLine(gx, 0, gx, h)

        # Zero line
        p.setPen(QPen(self.ZERO, 1))
        p.drawLine(0, cy, w, cy)

        if self._samples is None or len(self._samples) == 0:
            p.setPen(QColor(0x40, 0x40, 0x50))
            p.drawText(QRect(0, 0, w, h), Qt.AlignCenter, "no waveform")
            p.end()
            return

        n = len(self._samples)
        amp = cy - 2.0
        pen = QPen(self.LINE, 1)
        pen.setCosmetic(True)
        p.setPen(pen)

        # Min/max per pixel column for accuracy
        for x in range(w):
            s0 = int(x * n / w)
            s1 = int((x + 1) * n / w)
            s1 = max(s1, s0 + 1)
            s0 = min(s0, n - 1)
            s1 = min(s1, n)
            chunk = self._samples[s0:s1]
            y_top = int(cy - chunk.max() * amp)
            y_bot = int(cy - chunk.min() * amp)
            if y_top == y_bot:
                p.drawPoint(x, y_top)
            else:
                p.drawLine(x, y_top, x, y_bot)

        # Sample count label bottom-right
        font = p.font()
        font.setPointSize(8)
        p.setFont(font)
        p.setPen(self.LABEL_C)
        p.drawText(QRect(0, h - 18, w - 4, 16),
                   Qt.AlignRight | Qt.AlignVCenter,
                   f"{n} smp")

        p.end()


# ---------------------------------------------------------------------------
# Playback / export panel
# ---------------------------------------------------------------------------

# Log-scale slider: 0→1000 maps to 0.1x→10x
_SLIDER_STEPS = 1000
_SPEED_MIN = 0.1
_SPEED_MAX = 10.0


def _slider_to_speed(v: int) -> float:
    t = v / _SLIDER_STEPS
    return _SPEED_MIN * (_SPEED_MAX / _SPEED_MIN) ** t


def _speed_to_slider(speed: float) -> int:
    speed = max(_SPEED_MIN, min(_SPEED_MAX, speed))
    t = math.log(speed / _SPEED_MIN) / math.log(_SPEED_MAX / _SPEED_MIN)
    return int(t * _SLIDER_STEPS)


class PlaybackPanel(QWidget):
    """Right-side preview and export panel.

    Signals
    -------
    prev_requested : Signal()
    next_requested : Signal()
    play_all_requested : Signal(float, bool)
        Emitted with (speed, loop).
    stop_requested : Signal()
    export_requested : Signal()
    wave_name_changed : Signal(str)
    """

    prev_requested    = Signal()
    next_requested    = Signal()
    play_all_requested = Signal(float, bool)
    stop_requested    = Signal()
    export_requested  = Signal()
    wave_name_changed = Signal(str)

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state = state
        self._build()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_processed(self, waves: list[np.ndarray]) -> None:
        """Called after Go completes.  Enables controls, shows first wave."""
        has = len(waves) > 0
        for w in self._proc_widgets:
            w.setEnabled(has)
        if has:
            self.show_wave(0, len(waves))

    def show_wave(self, index: int, total: int) -> None:
        self._cycle_view.set_samples(
            self._state.processed_waves[index]
            if index < len(self._state.processed_waves) else None
        )
        self._counter_label.setText(
            f"Wave {index + 1:04d} / {total:04d}"
        )

    def set_playing(self, playing: bool) -> None:
        self._play_btn.setText("■ Stop" if playing else "▶ Play All")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(8)

        # ---- Cycle view ----
        self._cycle_view = CycleView()
        vbox.addWidget(self._cycle_view)

        # ---- Wave counter + nav buttons ----
        nav_grp = QGroupBox("WAVEFORM")
        nav_box = QVBoxLayout(nav_grp)
        nav_box.setSpacing(4)

        self._counter_label = QLabel("Wave 0000 / 0000")
        self._counter_label.setAlignment(Qt.AlignCenter)
        nav_box.addWidget(self._counter_label)

        btn_row = QHBoxLayout()
        self._prev_btn = QPushButton("◀ Prev")
        self._prev_btn.setProperty("secondary", True)
        self._next_btn = QPushButton("Next ▶")
        self._next_btn.setProperty("secondary", True)
        self._prev_btn.clicked.connect(self.prev_requested)
        self._next_btn.clicked.connect(self.next_requested)
        btn_row.addWidget(self._prev_btn)
        btn_row.addWidget(self._next_btn)
        nav_box.addLayout(btn_row)
        vbox.addWidget(nav_grp)

        # ---- Playback controls ----
        play_grp = QGroupBox("PLAYBACK")
        play_box = QVBoxLayout(play_grp)
        play_box.setSpacing(6)

        pb_row = QHBoxLayout()
        self._play_btn = QPushButton("▶ Play All")
        self._loop_chk = QCheckBox("Loop")
        self._play_btn.clicked.connect(self._on_play_stop)
        pb_row.addWidget(self._play_btn, 1)
        pb_row.addWidget(self._loop_chk)
        play_box.addLayout(pb_row)

        spd_row = QHBoxLayout()
        spd_row.addWidget(QLabel("Speed"))
        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setRange(0, _SLIDER_STEPS)
        self._speed_slider.setValue(_speed_to_slider(1.0))
        self._speed_slider.setToolTip("Playback speed (0.1x – 10x, log scale)")
        self._speed_label = QLabel("1.00×")
        self._speed_label.setFixedWidth(42)
        self._speed_slider.valueChanged.connect(self._on_speed_changed)
        spd_row.addWidget(self._speed_slider, 1)
        spd_row.addWidget(self._speed_label)
        play_box.addLayout(spd_row)

        vbox.addWidget(play_grp)

        # ---- Export ----
        exp_grp = QGroupBox("EXPORT")
        exp_box = QVBoxLayout(exp_grp)
        exp_box.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name"))
        self._name_edit = QLineEdit("wavebreach")
        self._name_edit.setPlaceholderText("wavetable name")
        self._name_edit.setToolTip("Base name for exported .wav files")
        self._name_edit.textChanged.connect(self.wave_name_changed)
        name_row.addWidget(self._name_edit, 1)
        exp_box.addLayout(name_row)

        self._export_btn = QPushButton("Export ZIP")
        self._export_btn.clicked.connect(self.export_requested)
        exp_box.addWidget(self._export_btn)

        vbox.addWidget(exp_grp)
        vbox.addStretch(1)

        # Collect all widgets that should be disabled until Go is pressed
        self._proc_widgets = [
            self._prev_btn, self._next_btn,
            self._play_btn, self._loop_chk, self._speed_slider,
            self._export_btn,
        ]
        for w in self._proc_widgets:
            w.setEnabled(False)

    # ------------------------------------------------------------------
    # Slot helpers
    # ------------------------------------------------------------------

    def _on_play_stop(self) -> None:
        # Toggle: if currently showing Stop, emit stop; else emit play
        if self._play_btn.text().startswith("■"):
            self.stop_requested.emit()
        else:
            speed = _slider_to_speed(self._speed_slider.value())
            loop  = self._loop_chk.isChecked()
            self.play_all_requested.emit(speed, loop)

    def _on_speed_changed(self, value: int) -> None:
        speed = _slider_to_speed(value)
        self._speed_label.setText(f"{speed:.2f}×")

    @property
    def wavetable_name(self) -> str:
        return self._name_edit.text().strip() or "wavebreach"

    @property
    def current_speed(self) -> float:
        return _slider_to_speed(self._speed_slider.value())

    @property
    def loop_enabled(self) -> bool:
        return self._loop_chk.isChecked()
