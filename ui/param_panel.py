"""
ui/param_panel.py
Left-side parameter panel.

All controls wired bidirectionally:
  - Start / End spinboxes each have a QSlider below them (range updates
    when a file is loaded).  Dragging the waveform marker also updates both.
  - Filter Cutoff has a QSlider (log-scale, 20-22000 Hz).
  - Filter Q has a QSlider (log-scale, 0.1-10.0).
  - The spectrum view's drag handle also updates these via set_cutoff() /
    set_q() called from MainWindow.

All sliders and spinboxes block each other's signals during programmatic
updates to avoid feedback loops.
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QSpinBox, QDoubleSpinBox,
    QRadioButton, QButtonGroup, QCheckBox, QPushButton,
    QSizePolicy, QFrame, QScrollArea, QSlider,
)

from core.state import AppState

# ---------------------------------------------------------------------------
# Log-scale helpers for cutoff and Q sliders
# ---------------------------------------------------------------------------

_CUTOFF_STEPS = 1000
_CUTOFF_MIN   = 20.0
_CUTOFF_MAX   = 22000.0

def _cutoff_to_slider(hz: float) -> int:
    hz = max(_CUTOFF_MIN, min(_CUTOFF_MAX, hz))
    t  = math.log10(hz / _CUTOFF_MIN) / math.log10(_CUTOFF_MAX / _CUTOFF_MIN)
    return int(t * _CUTOFF_STEPS)

def _slider_to_cutoff(v: int) -> float:
    t = v / _CUTOFF_STEPS
    return _CUTOFF_MIN * (_CUTOFF_MAX / _CUTOFF_MIN) ** t

_Q_STEPS = 1000
_Q_MIN   = 0.1
_Q_MAX   = 10.0

def _q_to_slider(q: float) -> int:
    q = max(_Q_MIN, min(_Q_MAX, q))
    t = math.log10(q / _Q_MIN) / math.log10(_Q_MAX / _Q_MIN)
    return int(t * _Q_STEPS)

def _slider_to_q(v: int) -> float:
    t = v / _Q_STEPS
    return _Q_MIN * (_Q_MAX / _Q_MIN) ** t


class ParamPanel(QWidget):
    """Left-side parameter panel.

    Signals
    -------
    go_requested : Signal()
    params_changed : Signal()
    """

    go_requested   = Signal()
    params_changed = Signal()

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state    = state
        self._building = True
        self._total_samples = 0   # updated on file load for marker sliders

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        self._layout = QVBoxLayout(inner)
        self._layout.setSpacing(8)
        self._layout.setContentsMargins(8, 8, 8, 8)

        self._build_slice_group()
        self._build_length_group()
        self._build_filter_group()
        self._build_normalize_group()
        self._build_modify_group()

        self._layout.addStretch(1)

        self._go_btn = QPushButton("GO")
        self._go_btn.setProperty("go", True)
        self._go_btn.setEnabled(False)
        self._go_btn.clicked.connect(self.go_requested)

        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll, 1)
        outer.addWidget(self._go_btn)

        self._building = False
        self._wire_simple_spins()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_file_loaded(self, loaded: bool, total_samples: int = 0) -> None:
        self._go_btn.setEnabled(loaded)
        if loaded and total_samples > 0:
            self._total_samples = total_samples
            # Update start/end slider ranges to match file length
            self._start_slider.blockSignals(True)
            self._start_slider.setRange(0, total_samples - 1)
            self._start_slider.setValue(self._start_spin.value())
            self._start_slider.blockSignals(False)

            self._end_slider.blockSignals(True)
            self._end_slider.setRange(0, total_samples - 1)
            self._end_slider.setValue(self._end_spin.value())
            self._end_slider.blockSignals(False)

            self._start_spin.setRange(0, total_samples - 1)
            self._end_spin.setRange(0, total_samples - 1)

    def set_avg_length(self, avg_samples: float) -> None:
        """Update the diagnostic average region length label (called from MainWindow)."""
        if avg_samples <= 0:
            self._avg_length_label.setText("avg: --")
        else:
            avg_hz = 44100.0 / avg_samples if avg_samples > 0 else 0.0
            self._avg_length_label.setText(
                f"avg: {avg_samples:.0f} smp  /  {avg_hz:.1f} Hz"
            )

    def set_start_pad(self, value: int) -> None:
        """Called externally (e.g. from waveform marker drag)."""
        self._start_spin.blockSignals(True)
        self._start_slider.blockSignals(True)
        self._start_spin.setValue(value)
        self._start_slider.setValue(value)
        self._start_spin.blockSignals(False)
        self._start_slider.blockSignals(False)
        self._emit_changed()

    def set_end_pad(self, value: int) -> None:
        """Called externally (e.g. from waveform marker drag)."""
        self._end_spin.blockSignals(True)
        self._end_slider.blockSignals(True)
        self._end_spin.setValue(value)
        self._end_slider.setValue(value)
        self._end_spin.blockSignals(False)
        self._end_slider.blockSignals(False)
        self._emit_changed()

    def set_cutoff(self, hz: float) -> None:
        """Called from spectrum view drag. Updates spinbox + slider."""
        self._filter_cutoff_spin.blockSignals(True)
        self._cutoff_slider.blockSignals(True)
        self._filter_cutoff_spin.setValue(hz)
        self._cutoff_slider.setValue(_cutoff_to_slider(hz))
        self._filter_cutoff_spin.blockSignals(False)
        self._cutoff_slider.blockSignals(False)
        self._emit_changed()

    def set_q(self, q: float) -> None:
        """Called from spectrum view drag. Updates spinbox + slider."""
        self._filter_q_spin.blockSignals(True)
        self._q_slider.blockSignals(True)
        self._filter_q_spin.setValue(q)
        self._q_slider.setValue(_q_to_slider(q))
        self._filter_q_spin.blockSignals(False)
        self._q_slider.blockSignals(False)
        self._emit_changed()

    def read_into_state(self) -> None:
        s = self._state
        s.start_pad    = self._start_spin.value()
        s.end_pad      = self._end_spin.value()
        s.num_waves    = self._num_spin.value()
        s.min_samples  = self._min_spin.value()
        s.max_samples  = self._max_spin.value()
        s.edge_mode    = self._edge_mode()

        s.length_mode    = "pitch" if self._length_pitch_rb.isChecked() else "samples"
        s.length_hz      = self._length_hz_spin.value()
        s.length_samples = self._length_smp_spin.value()

        s.filter_mode   = self._filter_mode()
        s.filter_cutoff = self._filter_cutoff_spin.value()
        s.filter_q      = self._filter_q_spin.value()

        s.normalize_enabled = self._norm_chk.isChecked()
        s.normalize_db      = self._norm_spin.value()

        s.offset_begin   = self._offset_begin.value()
        s.offset_end     = self._offset_end.value()
        s.stretch_begin  = self._stretch_begin.value()
        s.stretch_end    = self._stretch_end.value()
        s.suppress_begin = self._suppress_begin.value()
        s.suppress_end   = self._suppress_end.value()
        s.distribute_begin = self._distribute_begin.value()
        s.distribute_end   = self._distribute_end.value()

    # ------------------------------------------------------------------
    # Builder helpers
    # ------------------------------------------------------------------

    def _emit_changed(self) -> None:
        if not self._building:
            self.params_changed.emit()

    def _build_slice_group(self) -> None:
        grp  = QGroupBox("SLICE")
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(4)

        # ---- Edge direction filter ----
        edge_row = QHBoxLayout()
        edge_row.addWidget(QLabel("Edge"))
        self._edge_none_rb    = QRadioButton("None")
        self._edge_rising_rb  = QRadioButton("Rising")
        self._edge_falling_rb = QRadioButton("Falling")
        self._edge_none_rb.setChecked(True)
        self._edge_rb_group = QButtonGroup(self)
        for btn in (self._edge_none_rb, self._edge_rising_rb, self._edge_falling_rb):
            self._edge_rb_group.addButton(btn)
            edge_row.addWidget(btn)
        edge_row.addStretch()
        vbox.addLayout(edge_row)

        # ---- Start row + slider ----
        self._start_spin = self._make_int_spin(0, 0, 441000,
                                               "Samples from front to skip")
        start_row = QHBoxLayout()
        start_row.addWidget(QLabel("Start"))
        start_row.addWidget(self._start_spin, 1)
        start_row.addWidget(QLabel("smp"))
        vbox.addLayout(start_row)

        self._start_slider = QSlider(Qt.Horizontal)
        self._start_slider.setRange(0, 441000)
        self._start_slider.setValue(0)
        self._start_slider.setToolTip("Drag to set Start position")
        vbox.addWidget(self._start_slider)

        # ---- End row + slider ----
        self._end_spin = self._make_int_spin(0, 0, 441000,
                                             "Samples from end to skip")
        end_row = QHBoxLayout()
        end_row.addWidget(QLabel("End"))
        end_row.addWidget(self._end_spin, 1)
        end_row.addWidget(QLabel("smp"))
        vbox.addLayout(end_row)

        self._end_slider = QSlider(Qt.Horizontal)
        self._end_slider.setRange(0, 441000)
        self._end_slider.setValue(0)
        self._end_slider.setToolTip("Drag to set End position (samples from end)")
        vbox.addWidget(self._end_slider)

        # ---- Remaining fields in a grid ----
        self._num_spin = self._make_int_spin(16, 1, 9999,
                                             "Number of waveforms to extract")
        self._min_spin = self._make_int_spin(64, 1, 441000,
                                             "Ignore ZC gaps smaller than this")
        self._max_spin = self._make_int_spin(4096, 1, 441000,
                                             "Ignore ZC gaps larger than this")

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setColumnStretch(1, 1)
        for row, (label, widget, unit) in enumerate([
            ("Number", self._num_spin,   ""),
            ("Min ZC", self._min_spin,   "smp"),
            ("Max ZC", self._max_spin,   "smp"),
        ]):
            grid.addWidget(QLabel(label), row, 0, Qt.AlignRight)
            grid.addWidget(widget, row, 1)
            if unit:
                grid.addWidget(QLabel(unit), row, 2)
        vbox.addLayout(grid)

        # Bidirectional wiring: spin <-> slider
        self._start_spin.valueChanged.connect(self._on_start_spin_changed)
        self._start_slider.valueChanged.connect(self._on_start_slider_changed)
        self._end_spin.valueChanged.connect(self._on_end_spin_changed)
        self._end_slider.valueChanged.connect(self._on_end_slider_changed)

        # Edge mode radio buttons
        for rb in (self._edge_none_rb, self._edge_rising_rb, self._edge_falling_rb):
            rb.toggled.connect(self._emit_changed)

        self._layout.addWidget(grp)

    def _build_length_group(self) -> None:
        grp  = QGroupBox("LENGTH")
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(4)

        rb_layout = QHBoxLayout()
        self._length_pitch_rb   = QRadioButton("Pitch (Hz)")
        self._length_samples_rb = QRadioButton("Samples")
        self._length_samples_rb.setChecked(True)
        self._length_rb_group = QButtonGroup(self)
        self._length_rb_group.addButton(self._length_pitch_rb,   0)
        self._length_rb_group.addButton(self._length_samples_rb, 1)
        rb_layout.addWidget(self._length_pitch_rb)
        rb_layout.addWidget(self._length_samples_rb)
        rb_layout.addStretch()
        vbox.addLayout(rb_layout)

        hz_row = QHBoxLayout()
        self._length_hz_label = QLabel("Hz")
        self._length_hz_spin  = QDoubleSpinBox()
        self._length_hz_spin.setRange(20.0, 20000.0)
        self._length_hz_spin.setValue(440.0)
        self._length_hz_spin.setSingleStep(1.0)
        self._length_hz_spin.setDecimals(2)
        self._length_hz_spin.setToolTip("Target fundamental frequency")
        hz_row.addWidget(self._length_hz_label)
        hz_row.addWidget(self._length_hz_spin, 1)
        vbox.addLayout(hz_row)

        smp_row = QHBoxLayout()
        self._length_smp_label = QLabel("Smp")
        self._length_smp_spin  = QSpinBox()
        self._length_smp_spin.setRange(1, 441000)
        self._length_smp_spin.setValue(2048)
        self._length_smp_spin.setToolTip("Target length in samples")
        smp_row.addWidget(self._length_smp_label)
        smp_row.addWidget(self._length_smp_spin, 1)
        vbox.addLayout(smp_row)

        self._length_pitch_rb.toggled.connect(self._on_length_mode_changed)
        self._length_hz_spin.valueChanged.connect(self._on_hz_changed)
        self._length_smp_spin.valueChanged.connect(self._on_smp_changed)
        self._on_length_mode_changed(False)

        # Diagnostic: average actual region length from current selection
        self._avg_length_label = QLabel("avg: --")
        self._avg_length_label.setProperty("dim", True)
        self._avg_length_label.setToolTip(
            "Average actual cycle length of currently selected regions "
            "(before stretching) -- diagnostic only, not the stretch target"
        )
        vbox.addWidget(self._avg_length_label)

        self._layout.addWidget(grp)

    def _build_filter_group(self) -> None:
        grp  = QGroupBox("FILTER")
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(4)

        mode_row = QHBoxLayout()
        self._filter_lp  = QRadioButton("LP")
        self._filter_hp  = QRadioButton("HP")
        self._filter_bp  = QRadioButton("BP")
        self._filter_off = QRadioButton("Off")
        self._filter_lp.setChecked(True)
        self._filter_rb_group = QButtonGroup(self)
        for btn in (self._filter_lp, self._filter_hp, self._filter_bp, self._filter_off):
            self._filter_rb_group.addButton(btn)
            mode_row.addWidget(btn)
        mode_row.addStretch()
        vbox.addLayout(mode_row)

        # Disable cutoff/Q controls when Off is selected
        self._filter_off.toggled.connect(self._on_filter_off_toggled)

        # Cutoff spinbox
        cutoff_row = QHBoxLayout()
        cutoff_row.addWidget(QLabel("Cutoff"))
        self._filter_cutoff_spin = QDoubleSpinBox()
        self._filter_cutoff_spin.setRange(20.0, 22000.0)
        self._filter_cutoff_spin.setValue(8000.0)
        self._filter_cutoff_spin.setSingleStep(10.0)
        self._filter_cutoff_spin.setDecimals(1)
        self._filter_cutoff_spin.setToolTip("Filter cutoff (Hz) -- also drag on spectrum")
        cutoff_row.addWidget(self._filter_cutoff_spin, 1)
        cutoff_row.addWidget(QLabel("Hz"))
        vbox.addLayout(cutoff_row)

        # Cutoff slider (log scale)
        self._cutoff_slider = QSlider(Qt.Horizontal)
        self._cutoff_slider.setRange(0, _CUTOFF_STEPS)
        self._cutoff_slider.setValue(_cutoff_to_slider(8000.0))
        self._cutoff_slider.setToolTip("Cutoff frequency (log scale)")
        vbox.addWidget(self._cutoff_slider)

        # Q spinbox
        q_row = QHBoxLayout()
        q_row.addWidget(QLabel("Q"))
        self._filter_q_spin = QDoubleSpinBox()
        self._filter_q_spin.setRange(0.1, 10.0)
        self._filter_q_spin.setValue(0.707)
        self._filter_q_spin.setSingleStep(0.1)
        self._filter_q_spin.setDecimals(3)
        self._filter_q_spin.setToolTip("Resonance -- also drag up/down on spectrum")
        q_row.addWidget(self._filter_q_spin, 1)
        vbox.addLayout(q_row)

        # Q slider (log scale)
        self._q_slider = QSlider(Qt.Horizontal)
        self._q_slider.setRange(0, _Q_STEPS)
        self._q_slider.setValue(_q_to_slider(0.707))
        self._q_slider.setToolTip("Q / resonance (log scale)")
        vbox.addWidget(self._q_slider)

        # Bidirectional wiring
        self._filter_cutoff_spin.valueChanged.connect(self._on_cutoff_spin_changed)
        self._cutoff_slider.valueChanged.connect(self._on_cutoff_slider_changed)
        self._filter_q_spin.valueChanged.connect(self._on_q_spin_changed)
        self._q_slider.valueChanged.connect(self._on_q_slider_changed)

        for rb in (self._filter_lp, self._filter_hp, self._filter_bp, self._filter_off):
            rb.toggled.connect(self._emit_changed)

        self._layout.addWidget(grp)

    def _build_normalize_group(self) -> None:
        grp = QGroupBox("NORMALIZE")
        row = QHBoxLayout(grp)
        row.setSpacing(6)

        self._norm_chk = QCheckBox("Enable")
        self._norm_chk.setChecked(True)
        self._norm_spin = QDoubleSpinBox()
        self._norm_spin.setRange(-3.0, 0.0)
        self._norm_spin.setValue(0.0)
        self._norm_spin.setSingleStep(0.1)
        self._norm_spin.setDecimals(1)
        self._norm_spin.setSuffix(" dB")
        self._norm_spin.setToolTip("Peak normalize target (0.0 = full scale)")

        self._norm_chk.toggled.connect(lambda c: self._norm_spin.setEnabled(c))
        self._norm_chk.toggled.connect(self._emit_changed)
        self._norm_spin.valueChanged.connect(self._emit_changed)

        row.addWidget(self._norm_chk)
        row.addWidget(self._norm_spin, 1)
        self._layout.addWidget(grp)

    def _build_modify_group(self) -> None:
        grp  = QGroupBox("MODIFY")
        grid = QGridLayout(grp)
        grid.setSpacing(4)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        grid.addWidget(self._dim_label(""),      0, 0)
        grid.addWidget(self._dim_label("Begin"), 0, 1, Qt.AlignCenter)
        grid.addWidget(self._dim_label("End"),   0, 2, Qt.AlignCenter)

        self._offset_begin  = self._make_dbl_spin(-0.5, 0.5, 0.0, 0.01, 2)
        self._offset_end    = self._make_dbl_spin(-0.5, 0.5, 0.0, 0.01, 2)
        grid.addWidget(QLabel("Offset"),  1, 0, Qt.AlignRight)
        grid.addWidget(self._offset_begin, 1, 1)
        grid.addWidget(self._offset_end,   1, 2)

        self._stretch_begin = self._make_dbl_spin(-0.5, 0.5, 0.0, 0.01, 2)
        self._stretch_end   = self._make_dbl_spin(-0.5, 0.5, 0.0, 0.01, 2)
        grid.addWidget(QLabel("Stretch"), 2, 0, Qt.AlignRight)
        grid.addWidget(self._stretch_begin, 2, 1)
        grid.addWidget(self._stretch_end,   2, 2)

        self._suppress_begin = self._make_dbl_spin(-1.0, 1.0, 0.0, 0.01, 2)
        self._suppress_end   = self._make_dbl_spin(-1.0, 1.0, 0.0, 0.01, 2)
        grid.addWidget(QLabel("Suppress"), 3, 0, Qt.AlignRight)
        grid.addWidget(self._suppress_begin, 3, 1)
        grid.addWidget(self._suppress_end,   3, 2)

        # Distribute: -0.5 to +0.5, step 0.01
        self._distribute_begin = self._make_dbl_spin(-0.5, 0.5, 0.0, 0.01, 2)
        self._distribute_end   = self._make_dbl_spin(-0.5, 0.5, 0.0, 0.01, 2)
        grid.addWidget(QLabel("Distribute"), 4, 0, Qt.AlignRight)
        grid.addWidget(self._distribute_begin, 4, 1)
        grid.addWidget(self._distribute_end,   4, 2)

        for w in (self._offset_begin, self._offset_end,
                  self._stretch_begin, self._stretch_end,
                  self._suppress_begin, self._suppress_end,
                  self._distribute_begin, self._distribute_end):
            w.valueChanged.connect(self._emit_changed)

        self._layout.addWidget(grp)

    # ------------------------------------------------------------------
    # Widget factories
    # ------------------------------------------------------------------

    def _make_int_spin(self, default, lo, hi, tip="") -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(default)
        if tip:
            sb.setToolTip(tip)
        # NOTE: start/end spins wire their own signals below; others wire here
        return sb

    def _make_dbl_spin(self, lo, hi, default, step, decimals, tip="") -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(default)
        sb.setSingleStep(step)
        sb.setDecimals(decimals)
        if tip:
            sb.setToolTip(tip)
        sb.valueChanged.connect(self._emit_changed)
        return sb

    @staticmethod
    def _dim_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setProperty("dim", True)
        return lbl

    # ------------------------------------------------------------------
    # Bidirectional spin <-> slider handlers
    # (each blocks the other's signals to avoid loops)
    # ------------------------------------------------------------------

    def _on_start_spin_changed(self, v: int) -> None:
        self._start_slider.blockSignals(True)
        self._start_slider.setValue(v)
        self._start_slider.blockSignals(False)
        self._emit_changed()

    def _on_start_slider_changed(self, v: int) -> None:
        self._start_spin.blockSignals(True)
        self._start_spin.setValue(v)
        self._start_spin.blockSignals(False)
        self._emit_changed()

    def _on_end_spin_changed(self, v: int) -> None:
        self._end_slider.blockSignals(True)
        self._end_slider.setValue(v)
        self._end_slider.blockSignals(False)
        self._emit_changed()

    def _on_end_slider_changed(self, v: int) -> None:
        self._end_spin.blockSignals(True)
        self._end_spin.setValue(v)
        self._end_spin.blockSignals(False)
        self._emit_changed()

    def _on_cutoff_spin_changed(self, hz: float) -> None:
        self._cutoff_slider.blockSignals(True)
        self._cutoff_slider.setValue(_cutoff_to_slider(hz))
        self._cutoff_slider.blockSignals(False)
        self._emit_changed()

    def _on_cutoff_slider_changed(self, v: int) -> None:
        hz = _slider_to_cutoff(v)
        self._filter_cutoff_spin.blockSignals(True)
        self._filter_cutoff_spin.setValue(hz)
        self._filter_cutoff_spin.blockSignals(False)
        self._emit_changed()

    def _on_q_spin_changed(self, q: float) -> None:
        self._q_slider.blockSignals(True)
        self._q_slider.setValue(_q_to_slider(q))
        self._q_slider.blockSignals(False)
        self._emit_changed()

    def _on_q_slider_changed(self, v: int) -> None:
        q = _slider_to_q(v)
        self._filter_q_spin.blockSignals(True)
        self._filter_q_spin.setValue(q)
        self._filter_q_spin.blockSignals(False)
        self._emit_changed()

    # ------------------------------------------------------------------
    # Number / min / max emit
    # ------------------------------------------------------------------

    def _wire_simple_spins(self) -> None:
        for sb in (self._num_spin, self._min_spin, self._max_spin):
            sb.valueChanged.connect(self._emit_changed)

    # ------------------------------------------------------------------
    # Length mode cross-update
    # ------------------------------------------------------------------

    def _on_length_mode_changed(self, _=None) -> None:
        is_pitch = self._length_pitch_rb.isChecked()
        self._length_hz_spin.setEnabled(is_pitch)
        self._length_smp_spin.setEnabled(not is_pitch)
        self._emit_changed()

    def _on_hz_changed(self, hz: float) -> None:
        if self._length_pitch_rb.isChecked() and hz > 0:
            smp = int(round(44100.0 / hz))
            self._length_smp_spin.blockSignals(True)
            self._length_smp_spin.setValue(smp)
            self._length_smp_spin.blockSignals(False)
        self._emit_changed()

    def _on_smp_changed(self, smp: int) -> None:
        if self._length_samples_rb.isChecked() and smp > 0:
            hz = 44100.0 / smp
            self._length_hz_spin.blockSignals(True)
            self._length_hz_spin.setValue(hz)
            self._length_hz_spin.blockSignals(False)
        self._emit_changed()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _filter_mode(self) -> str:
        if self._filter_hp.isChecked():  return "HP"
        if self._filter_bp.isChecked():  return "BP"
        if self._filter_off.isChecked(): return "OFF"
        return "LP"

    def _edge_mode(self) -> str:
        if self._edge_rising_rb.isChecked():  return "rising"
        if self._edge_falling_rb.isChecked(): return "falling"
        return "none"

    def _on_filter_off_toggled(self, checked: bool) -> None:
        """Dim cutoff/Q controls when filter is Off."""
        enabled = not checked
        self._filter_cutoff_spin.setEnabled(enabled)
        self._cutoff_slider.setEnabled(enabled)
        self._filter_q_spin.setEnabled(enabled)
        self._q_slider.setEnabled(enabled)
