"""
ui/main_window.py
MainWindow for Wavebreach.

Orchestrates:
  - Top: WaveformView (full width)
  - File row: path label, Open button, Play button, Stop button
  - Middle: SpectrumView (full width)
  - Bottom split: ParamPanel (left) | PlaybackPanel (right)
  - Status bar

Phase 1: file load, waveform display, spectrum display, Play/Stop of raw audio.
Phase 2: live ZC detection + splitter wired to waveform overlay.
Phase 3+: Go pipeline, processed playback, export.
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
    """Loads audio in a background thread to keep UI responsive."""
    finished = Signal(object, int)    # (samples_array, sr)
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

    # Accepted audio extensions for the file dialog filter
    AUDIO_FILTER = (
        "Audio Files (*.wav *.aif *.aiff *.flac *.ogg *.mp3 *.m4a *.aac *.wma);;"
        "All Files (*)"
    )

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wavebreach")
        self.setMinimumSize(900, 700)
        self.resize(1200, 800)

        # Shared state
        self._state = AppState()
        self._playback = PlaybackController()
        self._load_thread: QThread | None = None

        # Build UI
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

        # ---- Waveform view (full width) ----
        self._wave_view = WaveformView()
        root.addWidget(self._wave_view)

        root.addWidget(self._make_divider())

        # ---- File row ----
        file_row = self._build_file_row()
        root.addLayout(file_row)

        root.addWidget(self._make_divider())

        # ---- Spectrum view (full width) ----
        self._spec_view = SpectrumView()
        root.addWidget(self._spec_view)

        root.addWidget(self._make_divider())

        # ---- Bottom split: params | preview ----
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

        # ---- Status bar ----
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.showMessage("Ready -- open an audio file to begin.")

        # ---- Signal wiring ----
        self._param_panel.go_requested.connect(self._on_go)
        self._param_panel.params_changed.connect(self._on_params_changed)

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
        if not path:
            return
        self._load_file(path)

    def _load_file(self, path: str) -> None:
        self.statusBar().showMessage(f"Loading {Path(path).name}...")
        self._wave_view.clear()
        self._spec_view.clear()
        self._path_label.setText(path)
        self._update_playback_buttons(False)
        self._param_panel.set_file_loaded(False)

        # Clear any previous ZC / selection state
        self._state.all_zero_crossings = []
        self._state.excluded_min = []
        self._state.excluded_max = []
        self._state.selected_waves = []
        self._state.processed_waves = []

        # Spin up background load thread
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

        # Default wavetable name from filename stem
        stem = Path(self._state.source_path).stem
        self._state.wavetable_name = stem

        # Update views
        self._wave_view.set_samples(samples)
        self._spec_view.set_samples(samples, sr)

        # Status
        duration = len(samples) / sr
        self.statusBar().showMessage(
            f"{Path(self._state.source_path).name}  |  "
            f"{duration:.3f}s  |  {len(samples):,} samples  |  {sr} Hz"
        )

        self._update_playback_buttons(True)
        self._param_panel.set_file_loaded(True)

        # Run initial Tier-1 ZC pass with current parameter defaults
        self._run_tier1()

    def _on_load_error(self, message: str) -> None:
        self._path_label.setText("Load failed")
        self.statusBar().showMessage("Error loading file.")
        QMessageBox.critical(self, "Load Error", message)

    # ------------------------------------------------------------------
    # Tier-1: ZC detection + splitter (lightweight, main thread)
    # ------------------------------------------------------------------

    def _on_params_changed(self) -> None:
        """Called on any parameter widget change. Reads state and re-runs Tier-1."""
        self._param_panel.read_into_state()
        self._run_tier1()

    def _run_tier1(self) -> None:
        """Re-detect ZCs, recompute exclusion zones, reselect regions, update overlay."""
        s = self._state
        if s.raw_samples is None or s.duration_samples == 0:
            return

        # 1. Detect all ZCs in the full array
        all_zcs = detect(s.raw_samples)
        s.all_zero_crossings = all_zcs

        # 2. Compute exclusion zones
        exc_min, exc_max = compute_exclusions(all_zcs, s.min_samples, s.max_samples)
        s.excluded_min = exc_min
        s.excluded_max = exc_max

        # 3. Filter to usable ZCs
        usable = filter_usable(
            all_zcs, exc_min, exc_max,
            s.start_pad, s.end_pad, s.duration_samples,
        )

        # 4. Select regions
        regions = select_regions(
            usable, s.num_waves,
            s.start_pad, s.end_pad, s.duration_samples,
        )
        s.selected_waves = regions

        # 5. Push to waveform view
        self._wave_view.set_regions(regions, exc_min, exc_max)

        # Update status with ZC counts
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
        # Phase 3: apply filter before playback. For now, raw.
        self._playback.play_array(self._state.raw_samples, self._state.sample_rate)
        self._update_playback_buttons(True)

    def _on_play_all(self, speed: float, loop: bool) -> None:
        """Play concatenated processed waves at given speed."""
        waves = self._state.processed_waves
        if not waves:
            return
        import numpy as np
        combined = np.concatenate(waves)
        effective_sr = int(self._state.sample_rate * speed)
        effective_sr = max(1000, min(effective_sr, 192000))
        self._playback.play_array(combined, effective_sr)
        self._playback_panel.set_playing(True)

    def _on_stop(self) -> None:
        self._playback.stop()
        self._playback_panel.set_playing(False)

    # ------------------------------------------------------------------
    # Waveform navigation
    # ------------------------------------------------------------------

    def _on_prev(self) -> None:
        if not self._state.processed_waves:
            return
        self._state.current_wave_index = max(
            0, self._state.current_wave_index - 1
        )
        self._playback_panel.show_wave(
            self._state.current_wave_index,
            len(self._state.processed_waves),
        )

    def _on_next(self) -> None:
        if not self._state.processed_waves:
            return
        self._state.current_wave_index = min(
            len(self._state.processed_waves) - 1,
            self._state.current_wave_index + 1,
        )
        self._playback_panel.show_wave(
            self._state.current_wave_index,
            len(self._state.processed_waves),
        )

    # ------------------------------------------------------------------
    # Go (Tier-2 -- Phase 3)
    # ------------------------------------------------------------------

    def _on_go(self) -> None:
        self._param_panel.read_into_state()
        self._run_tier1()
        # Phase 3: kick off DSP worker thread here.
        self.statusBar().showMessage(
            "GO: ZC selection updated. Full DSP pipeline coming in Phase 3."
        )

    # ------------------------------------------------------------------
    # Export (Phase 5)
    # ------------------------------------------------------------------

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
