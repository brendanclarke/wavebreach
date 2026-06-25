"""
ui/main_window.py
MainWindow for Wavebreach.

Phase 1 : file load, waveform/spectrum display, raw playback
Phase 2 : live ZC + splitter overlays
Phase 2b: zoom/pos sliders, draggable markers, spectrum filter drag
Phase 3 : Go button -> ProcessWorker (QThread) -> processed waveforms
          Filter applied to original-file preview playback
          Filter response overlay pushed to spectrum view
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QSizePolicy,
    QSplitter, QFrame, QStatusBar, QMessageBox,
    QProgressDialog,
)

from core.state import AppState
from core.audio_io import load_audio
from core.playback import PlaybackController
from core.zero_crossing import detect, compute_exclusions, filter_usable
from core.splitter import select_regions
from core.filter_dsp import design_filter, apply_filter, compute_response
from core.processor import ProcessWorker
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
        self._proc_thread: QThread | None = None
        self._progress_dlg: QProgressDialog | None = None

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

        self._wave_view = WaveformView()
        root.addWidget(self._wave_view)
        root.addWidget(self._make_divider())

        root.addLayout(self._build_file_row())
        root.addWidget(self._make_divider())

        self._spec_view = SpectrumView()
        root.addWidget(self._spec_view)
        root.addWidget(self._make_divider())

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

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready -- open an audio file to begin.")

        # ---- Signal wiring ----
        self._param_panel.go_requested.connect(self._on_go)
        self._param_panel.params_changed.connect(self._on_params_changed)

        self._wave_view.start_changed.connect(self._on_start_marker_dragged)
        self._wave_view.end_changed.connect(self._on_end_marker_dragged)

        self._spec_view.cutoff_changed.connect(self._param_panel.set_cutoff)
        self._spec_view.q_changed.connect(self._param_panel.set_q)

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
        self._state.excluded_min       = []
        self._state.excluded_max       = []
        self._state.selected_waves     = []
        self._state.processed_waves    = []

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
        self._param_panel.set_file_loaded(True, total_samples=len(samples))
        self._wave_view.set_markers(0, 0)

        self._sync_filter_display()
        self._run_tier1()

    def _on_load_error(self, message: str) -> None:
        self._path_label.setText("Load failed")
        self.statusBar().showMessage("Error loading file.")
        QMessageBox.critical(self, "Load Error", message)

    # ------------------------------------------------------------------
    # Marker drag callbacks
    # ------------------------------------------------------------------

    def _on_start_marker_dragged(self, val: int) -> None:
        self._param_panel.set_start_pad(val)

    def _on_end_marker_dragged(self, val: int) -> None:
        self._param_panel.set_end_pad(val)

    # ------------------------------------------------------------------
    # Tier-1: ZC detection + splitter (lightweight, main thread)
    # ------------------------------------------------------------------

    def _on_params_changed(self) -> None:
        self._param_panel.read_into_state()
        self._sync_filter_display()
        self._wave_view.set_markers(self._state.start_pad, self._state.end_pad)
        self._run_tier1()

    def _run_tier1(self) -> None:
        s = self._state
        if s.raw_samples is None or s.duration_samples == 0:
            return

        all_zcs = detect(s.raw_samples)
        s.all_zero_crossings = [zc[0] for zc in all_zcs]   # positions only for state

        exc_min, exc_max = compute_exclusions(all_zcs, s.min_samples, s.max_samples)
        s.excluded_min = exc_min
        s.excluded_max = exc_max

        usable = filter_usable(
            all_zcs, exc_min, exc_max,
            s.start_pad, s.end_pad, s.duration_samples,
            edge_mode=s.edge_mode,
        )

        regions = select_regions(
            usable, s.num_waves,
            s.start_pad, s.end_pad, s.duration_samples,
            edge_mode=s.edge_mode,
        )
        s.selected_waves = regions

        self._wave_view.set_regions(regions, exc_min, exc_max)

        # Compute average region length for diagnostic display
        if regions:
            avg_smp = sum(r.end_zc - r.begin_zc for r in regions) / len(regions)
        else:
            avg_smp = 0.0
        self._param_panel.set_avg_length(avg_smp)

        self.statusBar().showMessage(
            f"{Path(s.source_path).name}  |  "
            f"{len(all_zcs)} ZCs  |  {len(usable)} usable  |  "
            f"{len(regions)} regions selected"
        )

    # ------------------------------------------------------------------
    # Filter display sync (spectrum overlay + param panel display)
    # ------------------------------------------------------------------

    def _sync_filter_display(self) -> None:
        """Update spectrum filter marker and response overlay."""
        s = self._state
        self._spec_view.set_filter_params(s.filter_cutoff, s.filter_q, s.filter_mode)

        if s.filter_mode == "OFF":
            self._spec_view.set_filter_response(None, None)
            return

        try:
            sos = design_filter(s.filter_mode, s.filter_cutoff, s.filter_q, s.sample_rate)
            freqs, db = compute_response(sos, s.sample_rate)
            self._spec_view.set_filter_response(freqs, db)
        except Exception as exc:
            logger.warning("Filter response compute failed: %s", exc)

    # ------------------------------------------------------------------
    # Tier-2: Go button -> ProcessWorker
    # ------------------------------------------------------------------

    def _on_go(self) -> None:
        self._param_panel.read_into_state()
        self._run_tier1()

        s = self._state
        if not s.selected_waves:
            QMessageBox.warning(
                self, "Nothing to Process",
                "No valid waveform regions were found with the current parameters.\n"
                "Try adjusting Start, End, Min ZC, or Max ZC."
            )
            return

        # Progress dialog
        total = len(s.selected_waves)
        self._progress_dlg = QProgressDialog(
            "Processing waveforms...", "Cancel", 0, total, self
        )
        self._progress_dlg.setWindowTitle("Wavebreach")
        self._progress_dlg.setWindowModality(Qt.WindowModal)
        self._progress_dlg.setMinimumDuration(0)
        self._progress_dlg.setValue(0)

        # Worker thread
        self._proc_thread = QThread(self)
        self._proc_worker = ProcessWorker(s)
        self._proc_worker.moveToThread(self._proc_thread)

        self._proc_thread.started.connect(self._proc_worker.run)
        self._proc_worker.progress.connect(self._on_proc_progress)
        self._proc_worker.finished.connect(self._on_proc_finished)
        self._proc_worker.error.connect(self._on_proc_error)
        self._proc_worker.finished.connect(self._proc_thread.quit)
        self._proc_worker.error.connect(self._proc_thread.quit)
        self._progress_dlg.canceled.connect(self._proc_thread.requestInterruption)

        self._proc_thread.start()

    def _on_proc_progress(self, current: int, total: int) -> None:
        if self._progress_dlg:
            self._progress_dlg.setValue(current)

    def _on_proc_finished(self, waves: list) -> None:
        if self._progress_dlg:
            self._progress_dlg.close()
            self._progress_dlg = None

        self._state.processed_waves    = waves
        self._state.current_wave_index = 0

        self._playback_panel.set_processed(waves)
        if waves:
            self._playback_panel.show_wave(0, len(waves))

        self.statusBar().showMessage(
            f"Done -- {len(waves)} waveforms processed, "
            f"{len(waves[0]) if waves else 0} samples each."
        )

    def _on_proc_error(self, message: str) -> None:
        if self._progress_dlg:
            self._progress_dlg.close()
            self._progress_dlg = None
        QMessageBox.critical(self, "Processing Error", message)
        self.statusBar().showMessage("Processing failed.")

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def _on_play_original(self) -> None:
        """Play raw file with filter applied (or bypass if Off)."""
        s = self._state
        if s.raw_samples is None:
            return

        if s.filter_mode == "OFF":
            audio = s.raw_samples
        else:
            try:
                sos   = design_filter(s.filter_mode, s.filter_cutoff, s.filter_q, s.sample_rate)
                audio = apply_filter(s.raw_samples, sos)
            except Exception:
                audio = s.raw_samples

        self._playback.play_array(audio, s.sample_rate)

    def _on_play_all(self, speed: float, loop: bool) -> None:
        waves = self._state.processed_waves
        if not waves:
            return
        combined    = np.concatenate(waves)
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
