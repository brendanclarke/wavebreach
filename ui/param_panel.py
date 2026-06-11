"""
ui/param_panel.py
Left-side parameter panel.

Phase 1: All controls are created and laid out with correct types and ranges.
Signal wiring to AppState is stubbed — the GO button emits go_requested.
Full signal wiring to the live-update pipeline is Phase 2.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QSpinBox, QDoubleSpinBox,
    QRadioButton, QButtonGroup, QCheckBox, QPushButton,
    QSizePolicy, QFrame, QScrollArea,
)

from core.state import AppState


class ParamPanel(QWidget):
    """Left-side parameter panel.

    Signals
    -------
    go_requested : Signal()
        Emitted when the user clicks the GO button.
    params_changed : Signal()
        Emitted whenever any parameter widget changes value (for live
        Tier-1 updates to the waveform overlay).  Phase 2 will connect
        this to the ZC / splitter pipeline.
    """

    go_requested   = Signal()
    params_changed = Signal()

    def __init__(self, state: AppState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._state = state
        self._building = False    # suppress signals during initial build

        # Scroll area so params don't get clipped on small screens
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

        # GO button — outside scroll, always visible at bottom
        self._go_btn = QPushButton("GO")
        self._go_btn.setProperty("go", True)
        self._go_btn.setEnabled(False)          # enabled on file load
        self._go_btn.clicked.connect(self.go_requested)

        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll, 1)
        outer.addWidget(self._go_btn)

        self._building = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_file_loaded(self, loaded: bool) -> None:
        """Enable/disable GO button based on whether a file is loaded."""
        self._go_btn.setEnabled(loaded)

    def read_into_state(self) -> None:
        """Push all current widget values into AppState."""
        s = self._state

        s.start_pad    = self._start_spin.value()
        s.end_pad      = self._end_spin.value()
        s.num_waves    = self._num_spin.value()
        s.min_samples  = self._min_spin.value()
        s.max_samples  = self._max_spin.value()

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

    # ------------------------------------------------------------------
    # Builder helpers
    # ------------------------------------------------------------------

    def _emit_changed(self) -> None:
        if not self._building:
            self.params_changed.emit()

    def _build_slice_group(self) -> None:
        grp = QGroupBox("SLICE")
        grid = QGridLayout(grp)
        grid.setSpacing(4)
        grid.setColumnStretch(1, 1)

        self._start_spin = self._make_int_spin(0, 0, 441000, "samples from front to skip")
        self._end_spin   = self._make_int_spin(0, 0, 441000, "samples from end to skip")
        self._num_spin   = self._make_int_spin(16, 1, 9999,  "number of waveforms to extract")
        self._min_spin   = self._make_int_spin(64, 1, 441000,"ignore ZC gaps < this (samples)")
        self._max_spin   = self._make_int_spin(4096, 1, 441000,"ignore ZC gaps > this (samples)")

        rows = [
            ("Start",  self._start_spin, "smp"),
            ("End",    self._end_spin,   "smp"),
            ("Number", self._num_spin,   ""),
            ("Min ZC", self._min_spin,   "smp"),
            ("Max ZC", self._max_spin,   "smp"),
        ]
        for row, (label, widget, unit) in enumerate(rows):
            grid.addWidget(QLabel(label), row, 0, Qt.AlignRight)
            grid.addWidget(widget,        row, 1)
            if unit:
                grid.addWidget(QLabel(unit), row, 2)

        self._layout.addWidget(grp)

    def _build_length_group(self) -> None:
        grp = QGroupBox("LENGTH")
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(4)

        # Radio buttons
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

        # Hz spin (editable when pitch mode)
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

        # Samples spin (editable when samples mode)
        smp_row = QHBoxLayout()
        self._length_smp_label = QLabel("Smp")
        self._length_smp_spin  = QSpinBox()
        self._length_smp_spin.setRange(1, 441000)
        self._length_smp_spin.setValue(2048)
        self._length_smp_spin.setToolTip("Target length in samples")
        smp_row.addWidget(self._length_smp_label)
        smp_row.addWidget(self._length_smp_spin, 1)
        vbox.addLayout(smp_row)

        # Wire cross-update
        self._length_pitch_rb.toggled.connect(self._on_length_mode_changed)
        self._length_hz_spin.valueChanged.connect(self._on_hz_changed)
        self._length_smp_spin.valueChanged.connect(self._on_smp_changed)
        self._on_length_mode_changed(False)   # set initial enabled state

        self._layout.addWidget(grp)

    def _build_filter_group(self) -> None:
        grp = QGroupBox("FILTER")
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(4)

        # Mode radio
        mode_row = QHBoxLayout()
        self._filter_lp = QRadioButton("LP")
        self._filter_hp = QRadioButton("HP")
        self._filter_bp = QRadioButton("BP")
        self._filter_lp.setChecked(True)
        self._filter_rb_group = QButtonGroup(self)
        for btn in (self._filter_lp, self._filter_hp, self._filter_bp):
            self._filter_rb_group.addButton(btn)
            mode_row.addWidget(btn)
        mode_row.addStretch()
        vbox.addLayout(mode_row)

        # Cutoff
        cutoff_row = QHBoxLayout()
        cutoff_row.addWidget(QLabel("Cutoff"))
        self._filter_cutoff_spin = QDoubleSpinBox()
        self._filter_cutoff_spin.setRange(20.0, 22000.0)
        self._filter_cutoff_spin.setValue(8000.0)
        self._filter_cutoff_spin.setSingleStep(10.0)
        self._filter_cutoff_spin.setDecimals(1)
        self._filter_cutoff_spin.setToolTip("Filter cutoff frequency (Hz)")
        cutoff_row.addWidget(self._filter_cutoff_spin, 1)
        cutoff_row.addWidget(QLabel("Hz"))
        vbox.addLayout(cutoff_row)

        # Q
        q_row = QHBoxLayout()
        q_row.addWidget(QLabel("Q"))
        self._filter_q_spin = QDoubleSpinBox()
        self._filter_q_spin.setRange(0.1, 10.0)
        self._filter_q_spin.setValue(0.707)
        self._filter_q_spin.setSingleStep(0.1)
        self._filter_q_spin.setDecimals(3)
        self._filter_q_spin.setToolTip("Resonance (0.1 = wide, 10 = sharp peak)")
        q_row.addWidget(self._filter_q_spin, 1)
        vbox.addLayout(q_row)

        # Wire signals
        for w in (self._filter_cutoff_spin, self._filter_q_spin):
            w.valueChanged.connect(self._emit_changed)
        for rb in (self._filter_lp, self._filter_hp, self._filter_bp):
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

        self._norm_chk.toggled.connect(lambda checked: self._norm_spin.setEnabled(checked))
        self._norm_chk.toggled.connect(self._emit_changed)
        self._norm_spin.valueChanged.connect(self._emit_changed)

        row.addWidget(self._norm_chk)
        row.addWidget(self._norm_spin, 1)

        self._layout.addWidget(grp)

    def _build_modify_group(self) -> None:
        grp = QGroupBox("MODIFY")
        grid = QGridLayout(grp)
        grid.setSpacing(4)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        # Headers
        grid.addWidget(self._dim_label(""), 0, 0)
        grid.addWidget(self._dim_label("Begin"), 0, 1, Qt.AlignCenter)
        grid.addWidget(self._dim_label("End"),   0, 2, Qt.AlignCenter)

        # Offset: -0.5 to +0.5, step 0.01
        self._offset_begin  = self._make_dbl_spin(-0.5, 0.5, 0.0, 0.01, 2)
        self._offset_end    = self._make_dbl_spin(-0.5, 0.5, 0.0, 0.01, 2)
        grid.addWidget(QLabel("Offset"),         1, 0, Qt.AlignRight)
        grid.addWidget(self._offset_begin,       1, 1)
        grid.addWidget(self._offset_end,         1, 2)

        # Stretch: -0.5 to +0.5, step 0.01
        self._stretch_begin = self._make_dbl_spin(-0.5, 0.5, 0.0, 0.01, 2)
        self._stretch_end   = self._make_dbl_spin(-0.5, 0.5, 0.0, 0.01, 2)
        grid.addWidget(QLabel("Stretch"),        2, 0, Qt.AlignRight)
        grid.addWidget(self._stretch_begin,      2, 1)
        grid.addWidget(self._stretch_end,        2, 2)

        # Suppress: -1.0 to +1.0, step 0.01
        self._suppress_begin = self._make_dbl_spin(-1.0, 1.0, 0.0, 0.01, 2)
        self._suppress_end   = self._make_dbl_spin(-1.0, 1.0, 0.0, 0.01, 2)
        grid.addWidget(QLabel("Suppress"),       3, 0, Qt.AlignRight)
        grid.addWidget(self._suppress_begin,     3, 1)
        grid.addWidget(self._suppress_end,       3, 2)

        for w in (
            self._offset_begin, self._offset_end,
            self._stretch_begin, self._stretch_end,
            self._suppress_begin, self._suppress_end,
        ):
            w.valueChanged.connect(self._emit_changed)

        self._layout.addWidget(grp)

    # ------------------------------------------------------------------
    # Widget factories
    # ------------------------------------------------------------------

    def _make_int_spin(
        self, default: int, lo: int, hi: int, tip: str = ""
    ) -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(default)
        if tip:
            sb.setToolTip(tip)
        sb.valueChanged.connect(self._emit_changed)
        return sb

    def _make_dbl_spin(
        self, lo: float, hi: float, default: float,
        step: float, decimals: int, tip: str = ""
    ) -> QDoubleSpinBox:
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
    # Length mode cross-update
    # ------------------------------------------------------------------

    def _on_length_mode_changed(self, pitch_checked: bool) -> None:
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
        if self._filter_hp.isChecked():
            return "HP"
        if self._filter_bp.isChecked():
            return "BP"
        return "LP"
