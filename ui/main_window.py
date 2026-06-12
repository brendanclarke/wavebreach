"""
ui/main_window.py
MainWindow for Wavebreach.

Phase 1: file load, waveform display, spectrum display, raw playback.
Phase 2: live ZC + splitter wired to waveform overlays.
Phase 2b: zoom/pos sliders on waveform; draggable Start/End markers;
          draggable cutoff/Q on spectrum; all sliders in param panel.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QSizePolicy,
    QSplitter, QFrame, QStatusBar, QMessageBox,
)

from core.state import AppState
from core.audio_io import load_audio
from core.playback import PlaybackController
from core.zero_crossing import detect, compute_exclusions, filter_usable
from core.splitter import select_regions
from ui.waveform_view import WaveformView
from ui.spectrum_view import SpectrumView
from ui.param_panel import ParamPanel
from ui.playback_panel import PlaybackPanel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background loader thread
# ---------------------------------------------------------------------------

class _LoadWorker(QObject):
    finished = Signal(object, int)
    error    = Signal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self._path = path

    def run(self) -> None:
        try:
            samples, sr = load_audio(self._path)
            self.finished.emit(samples, sr)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):

    AUDIO_FILTER = (
        "Audio Files (*.wav *.aif *.aiff *.flac *.ogg *.mp3 *.m4a *.aac *.wma);;"
        "All Files (*)"
    )

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wavebreach")
        self.setMinimumSize(900, 700)
        self.resize(1200, 800)

        self._state    = AppState()
        self._playback = PlaybackController()
        self._load_thread: QThread | None = None

        self._build_ui()
        self._update_playback_buttons(False)

        if not self._playback.available:
            self.statusBar().showMessage(
                "Audio playback unavailable (sounddevice / PortAudio not found)."
            )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Waveform view (includes zoom/pos sliders internally)
        self._wave_view = WaveformView()
        root.addWidget(self._wave_view)

        root.addWidget(self._make_divider())

        # File row
        root.addLayout(self._build_file_row())

        root.addWidget(self._make_divider())

        # Spectrum view
        self._spec_view = SpectrumView()
        root.addWidget(self._spec_view)

        root.addWidget(self._make_divider())

        # Bottom split
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        self._param_panel    = ParamPanel(self._state)
        self._playback_panel = PlaybackPanel(self._state)
        self._param_panel.setMinimumWidth(300)
        self._playback_panel.setMinimumWidth(300)

        splitter.addWidget(self._param_panel)
        splitter.addWidget(self._playback_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        # Status bar
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready -- open an audio file to begin.")

        # ---- Signal wiring ----

        # Param panel
        self._param_panel.go_requested.connect(self._on_go)
        self._param_panel.params_changed.connect(self._on_params_changed)

        # Waveform marker drags -> param panel spinboxes/sliders
        self._wave_view.start_changed.connect(self._on_start_marker_dragged)
        self._wave_view.end_changed.connect(self._on_end_marker_dragged)

        # Spectrum drag -> param panel cutoff/Q
        self._spec_view.cutoff_changed.connect(self._param_panel.set_cutoff)
        self._spec_view.q_changed.connect(self._param_panel.set_q)

        # Playback panel
        self._playback_panel.prev_requested.connect(self._on_prev)
        self._playback_panel.next_requested.connect(self._on_next)
        self._playback_panel.play_all_requested.connect(self._on_play_all)
        self._playback_panel.stop_requested.connect(self._on_stop)
        self._playback_panel.export_requested.connect(self._on_export)
        self._playback_panel.wave_name_changed.connect(self._on_name_changed)

    def _build_file_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)

        self._path_label = QLabel("No file loaded")
        self._path_label.setProperty("dim", True)
        self._path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self._open_btn = QPushButton("Open...")
        self._open_btn.setProperty("secondary", True)
        self._open_btn.setFixedWidth(70)
        self._open_btn.clicked.connect(self._on_open)

        self._play_btn = QPushButton("Play")
        self._play_btn.setProperty("secondary", True)
        self._play_btn.setFixedWidth(70)
        self._play_btn.clicked.connect(self._on_play_original)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setProperty("secondary", True)
        self._stop_btn.setFixedWidth(70)
        self._stop_btn.clicked.connect(self._on_stop)

        row.addWidget(self._path_label, 1)
        row.addWidget(self._open_btn)
        row.addWidget(self._play_btn)
        row.addWidget(self._stop_btn)
        return row

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Audio File", "", self.AUDIO_FILTER
        )
        if path:
            self._load_file(path)

    def _load_file(self, path: str) -> None:
        self.statusBar().showMessage(f"Loading {Path(path).name}...")
        self._wave_view.clear()
        self._spec_view.clear()
        self._path_label.setText(path)
        self._update_playback_buttons(False)
        self._param_panel.set_file_loaded(False)

        self._state.all_zero_crossings = []
        self._state.excluded_min = []
        self._state.excluded_max = []
        self._state.selected_waves = []
        self._state.processed_waves = []

        self._load_thread = QThread(self)
        self._worker = _LoadWorker(path)
        self._worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_load_finished)
        self._worker.error.connect(self._on_load_error)
        self._worker.finished.connect(self._load_thread.quit)
        self._worker.error.connect(self._load_thread.quit)
        self._load_thread.start()

    def _on_load_finished(self, samples, sr: int) -> None:
        self._state.raw_samples      = samples
        self._state.sample_rate      = sr
        self._state.duration_samples = len(samples)
        self._state.source_path      = self._path_label.text()
        self._state.wavetable_name   = Path(self._state.source_path).stem

        self._wave_view.set_samples(samples)
        self._spec_view.set_samples(samples, sr)

        duration = len(samples) / sr
        self.statusBar().showMessage(
            f"{Path(self._state.source_path).name}  |  "
            f"{duration:.3f}s  |  {len(samples):,} samples  |  {sr} Hz"
        )

        self._update_playback_buttons(True)
        # Pass total_samples so Start/End sliders get correct range
        self._param_panel.set_file_loaded(True, total_samples=len(samples))

        # Initial markers at 0 / 0
        self._wave_view.set_markers(0, 0)

        # Sync spectrum display with current filter params
        self._spec_view.set_filter_params(
            self._state.filter_cutoff,
            self._state.filter_q,
            self._state.filter_mode,
        )

        self._run_tier1()

    def _on_load_error(self, message: str) -> None:
        self._path_label.setText("Load failed")
        self.statusBar().showMessage("Error loading file.")
        QMessageBox.critical(self, "Load Error", message)

    # ------------------------------------------------------------------
    # Marker drag callbacks
    # ------------------------------------------------------------------

    def _on_start_marker_dragged(self, val: int) -> None:
        """Waveform canvas dragged start marker -- push to param panel."""
        self._param_panel.set_start_pad(val)
        # params_changed will fire from set_start_pad -> _emit_changed

    def _on_end_marker_dragged(self, val: int) -> None:
        """Waveform canvas dragged end marker -- push to param panel."""
        self._param_panel.set_end_pad(val)

    # ------------------------------------------------------------------
    # Tier-1: ZC detection + splitter
    # ------------------------------------------------------------------

    def _on_params_changed(self) -> None:
        self._param_panel.read_into_state()
        # Keep spectrum display in sync with filter param changes
        self._spec_view.set_filter_params(
            self._state.filter_cutoff,
            self._state.filter_q,
            self._state.filter_mode,
        )
        # Keep waveform markers in sync with spinbox changes
        self._wave_view.set_markers(
            self._state.start_pad,
            self._state.end_pad,
        )
        self._run_tier1()

    def _run_tier1(self) -> None:
        s = self._state
        if s.raw_samples is None or s.duration_samples == 0:
            return

        all_zcs = detect(s.raw_samples)
        s.all_zero_crossings = all_zcs

        exc_min, exc_max = compute_exclusions(all_zcs, s.min_samples, s.max_samples)
        s.excluded_min = exc_min
        s.excluded_max = exc_max

        usable = filter_usable(
            all_zcs, exc_min, exc_max,
            s.start_pad, s.end_pad, s.duration_samples,
        )

        regions = select_regions(
            usable, s.num_waves,
            s.start_pad, s.end_pad, s.duration_samples,
        )
        s.selected_waves = regions

        self._wave_view.set_regions(regions, exc_min, exc_max)

        self.statusBar().showMessage(
            f"{Path(s.source_path).name}  |  "
            f"{len(all_zcs)} ZCs  |  "
            f"{len(usable)} usable  |  "
            f"{len(regions)} regions selected"
        )

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def _on_play_original(self) -> None:
        if self._state.raw_samples is None:
            return
        self._playback.play_array(self._state.raw_samples, self._state.sample_rate)
        self._update_playback_buttons(True)

    def _on_play_all(self, speed: float, loop: bool) -> None:
        waves = self._state.processed_waves
        if not waves:
            return
        import numpy as np
        combined = np.concatenate(waves)
        effective_sr = max(1000, min(int(self._state.sample_rate * speed), 192000))
        self._playback.play_array(combined, effective_sr)
        self._playback_panel.set_playing(True)

    def _on_stop(self) -> None:
        self._playback.stop()
        self._playback_panel.set_playing(False)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _on_prev(self) -> None:
        if not self._state.processed_waves:
            return
        self._state.current_wave_index = max(0, self._state.current_wave_index - 1)
        self._playback_panel.show_wave(
            self._state.current_wave_index, len(self._state.processed_waves))

    def _on_next(self) -> None:
        if not self._state.processed_waves:
            return
        self._state.current_wave_index = min(
            len(self._state.processed_waves) - 1,
            self._state.current_wave_index + 1)
        self._playback_panel.show_wave(
            self._state.current_wave_index, len(self._state.processed_waves))

    # ------------------------------------------------------------------
    # Go / Export
    # ------------------------------------------------------------------

    def _on_go(self) -> None:
        self._param_panel.read_into_state()
        self._run_tier1()
        self.statusBar().showMessage(
            "GO: ZC selection updated. Full DSP pipeline coming in Phase 3."
        )

    def _on_export(self) -> None:
        self.statusBar().showMessage("Export not yet implemented (Phase 5).")

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _on_name_changed(self, name: str) -> None:
        self._state.wavetable_name = name.strip() or "wavebreach"

    def _update_playback_buttons(self, has_file: bool) -> None:
        self._play_btn.setEnabled(has_file and self._playback.available)
        self._stop_btn.setEnabled(has_file and self._playback.available)

    @staticmethod
    def _make_divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setFixedHeight(1)
        line.setStyleSheet("background-color: #BBBBBB;")
        return line
