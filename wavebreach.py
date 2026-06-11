#!/usr/bin/env python3
"""
wavebreach.py
Entry point for Wavebreach.

Usage:
    python wavebreach.py [audio_file]

The optional positional argument opens a file immediately on launch,
which is convenient for drag-and-drop onto the script icon.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from ui.styles import LIGHT_STYLE
from ui.main_window import MainWindow

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("wavebreach")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # High-DPI support (Qt 6 handles this automatically, but be explicit)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Wavebreach")
    app.setOrganizationName("Wavebreach")
    app.setApplicationDisplayName("Wavebreach")

    # Apply stylesheet
    app.setStyleSheet(LIGHT_STYLE)

    # Prefer a monospaced fallback font if IBM Plex Mono isn't installed
    # (the QSS font-family cascade handles this, but set a sensible app default)
    font = QFont("Consolas", 10)
    font.setStyleHint(QFont.Monospace)
    app.setFont(font)

    window = MainWindow()
    window.show()

    # Optional: open file passed as command-line argument
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if Path(path).is_file():
            logger.info("Opening file from command line: %s", path)
            window._load_file(path)
        else:
            logger.warning("Command-line path not found: %s", path)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
