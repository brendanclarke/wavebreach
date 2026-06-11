"""
ui/styles.py - QSS stylesheet strings for Wavebreach.

Light theme is the default.  Dark theme is a second string that can be
applied by calling QApplication.instance().setStyleSheet(DARK_STYLE).

Design direction: industrial/utilitarian.  Think rack-mount hardware --
clean, functional, no decorative flourish.  Monospaced labels, tight
spacing, sharp corners, a controlled palette.

Palette (light):
  bg_primary   #F0F0EE   -- off-white, warm
  bg_secondary #E2E2DF   -- panel background
  bg_surface   #FFFFFF   -- widget insets (spinboxes, line edits)
  border       #BBBBBB   -- all borders
  text_primary #1A1A1A   -- near-black
  text_dim     #666666   -- secondary labels
  accent       #3A7BFF   -- buttons, highlights
  accent_dim   #1F5ACC   -- pressed state
  danger       #CC3333   -- validation errors
  wave_line    #3A7BFF   -- waveform draw colour
  wave_bg      #1A1A1F   -- waveform canvas background (always dark for contrast)
"""

LIGHT_STYLE = """
/* ---- Global ---- */
QMainWindow, QDialog {
    background-color: #F0F0EE;
    font-family: "IBM Plex Mono", "Consolas", "Courier New", monospace;
    font-size: 11px;
    color: #1A1A1A;
}

QWidget {
    background-color: #F0F0EE;
    color: #1A1A1A;
    font-family: "IBM Plex Mono", "Consolas", "Courier New", monospace;
    font-size: 11px;
}

/* ---- Panels / group boxes ---- */
QGroupBox {
    background-color: #E2E2DF;
    border: 1px solid #BBBBBB;
    border-radius: 2px;
    margin-top: 18px;
    padding-top: 6px;
    font-size: 10px;
    font-weight: bold;
    color: #444444;
    letter-spacing: 1px;
    text-transform: uppercase;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    top: 3px;
    padding: 0 4px;
    background-color: #E2E2DF;
}

/* ---- Labels ---- */
QLabel {
    background: transparent;
    color: #1A1A1A;
}
QLabel[dim="true"] {
    color: #666666;
    font-size: 10px;
}

/* ---- Buttons ---- */
QPushButton {
    background-color: #3A7BFF;
    color: #FFFFFF;
    border: none;
    border-radius: 2px;
    padding: 5px 14px;
    font-family: "IBM Plex Mono", "Consolas", "Courier New", monospace;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.5px;
    min-height: 26px;
}
QPushButton:hover {
    background-color: #5090FF;
}
QPushButton:pressed {
    background-color: #1F5ACC;
}
QPushButton:disabled {
    background-color: #AAAAAA;
    color: #EEEEEE;
}

QPushButton[secondary="true"] {
    background-color: #E2E2DF;
    color: #1A1A1A;
    border: 1px solid #BBBBBB;
}
QPushButton[secondary="true"]:hover {
    background-color: #D0D0CC;
}
QPushButton[secondary="true"]:pressed {
    background-color: #BBBBBB;
}

QPushButton[go="true"] {
    background-color: #1A1A1A;
    color: #FFFFFF;
    font-size: 13px;
    letter-spacing: 2px;
    min-height: 34px;
    border-radius: 2px;
}
QPushButton[go="true"]:hover {
    background-color: #3A3A3A;
}
QPushButton[go="true"]:pressed {
    background-color: #000000;
}
QPushButton[go="true"]:disabled {
    background-color: #888888;
}

/* ---- Spin boxes / line edits ---- */
QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #BBBBBB;
    border-radius: 2px;
    padding: 2px 6px;
    color: #1A1A1A;
    font-family: "IBM Plex Mono", "Consolas", "Courier New", monospace;
    font-size: 11px;
    selection-background-color: #3A7BFF;
    min-height: 22px;
}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border-color: #3A7BFF;
}
QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {
    background-color: #E8E8E5;
    color: #888888;
}
QSpinBox[error="true"], QDoubleSpinBox[error="true"], QLineEdit[error="true"] {
    border-color: #CC3333;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 14px;
    border-left: 1px solid #BBBBBB;
    border-bottom: 1px solid #BBBBBB;
    background: #E2E2DF;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 14px;
    border-left: 1px solid #BBBBBB;
    background: #E2E2DF;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #555555;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #555555;
}

/* ---- Radio buttons / checkboxes ---- */
QRadioButton, QCheckBox {
    spacing: 6px;
    color: #1A1A1A;
    background: transparent;
}
QRadioButton::indicator, QCheckBox::indicator {
    width: 13px;
    height: 13px;
    border: 1px solid #BBBBBB;
    background: #FFFFFF;
}
QRadioButton::indicator {
    border-radius: 7px;
}
QRadioButton::indicator:checked {
    background: #3A7BFF;
    border-color: #3A7BFF;
}
QCheckBox::indicator:checked {
    background: #3A7BFF;
    border-color: #3A7BFF;
    image: none;
}

/* ---- Sliders ---- */
QSlider::groove:horizontal {
    height: 3px;
    background: #CCCCCC;
    border-radius: 1px;
    margin: 0 2px;
}
QSlider::handle:horizontal {
    background: #3A7BFF;
    border: none;
    width: 12px;
    height: 12px;
    border-radius: 6px;
    margin: -5px 0;
}
QSlider::sub-page:horizontal {
    background: #3A7BFF;
    border-radius: 1px;
}

/* ---- Scroll bars ---- */
QScrollBar:vertical {
    width: 8px;
    background: #E2E2DF;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #BBBBBB;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ---- Status bar ---- */
QStatusBar {
    background-color: #E2E2DF;
    border-top: 1px solid #BBBBBB;
    color: #444444;
    font-size: 10px;
}

/* ---- Tooltip ---- */
QToolTip {
    background-color: #1A1A1A;
    color: #F0F0EE;
    border: none;
    padding: 4px 8px;
    font-size: 10px;
    border-radius: 2px;
}

/* ---- Splitter ---- */
QSplitter::handle {
    background: #BBBBBB;
}
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical   { height: 1px; }

/* ---- Scroll area ---- */
QScrollArea {
    border: none;
    background: transparent;
}
"""

# ---------------------------------------------------------------------------
# Dark theme -- swap in later if desired
# ---------------------------------------------------------------------------
DARK_STYLE = """
QMainWindow, QDialog, QWidget {
    background-color: #1A1A1F;
    color: #E0E0DC;
    font-family: "IBM Plex Mono", "Consolas", "Courier New", monospace;
    font-size: 11px;
}
QGroupBox {
    background-color: #22222A;
    border: 1px solid #3A3A4A;
    border-radius: 2px;
    margin-top: 18px;
    padding-top: 6px;
    font-size: 10px;
    font-weight: bold;
    color: #888888;
    letter-spacing: 1px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px; top: 3px; padding: 0 4px;
    background-color: #22222A;
}
QLabel { background: transparent; color: #E0E0DC; }
QPushButton {
    background-color: #3A7BFF; color: #FFFFFF;
    border: none; border-radius: 2px; padding: 5px 14px;
    font-family: "IBM Plex Mono", "Consolas", monospace;
    font-size: 11px; font-weight: bold; min-height: 26px;
}
QPushButton:hover  { background-color: #5090FF; }
QPushButton:pressed{ background-color: #1F5ACC; }
QPushButton:disabled{ background-color: #333340; color: #666666; }
QPushButton[secondary="true"] {
    background-color: #2A2A35; color: #E0E0DC; border: 1px solid #3A3A4A;
}
QPushButton[secondary="true"]:hover { background-color: #33333F; }
QPushButton[go="true"] {
    background-color: #E0E0DC; color: #1A1A1F;
    font-size: 13px; letter-spacing: 2px; min-height: 34px;
}
QPushButton[go="true"]:hover  { background-color: #FFFFFF; }
QPushButton[go="true"]:pressed{ background-color: #BBBBBB; }
QPushButton[go="true"]:disabled{ background-color: #333340; color: #666666; }
QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #0E0E14; border: 1px solid #3A3A4A;
    border-radius: 2px; padding: 2px 6px; color: #E0E0DC;
    font-family: "IBM Plex Mono", "Consolas", monospace;
    font-size: 11px; min-height: 22px;
    selection-background-color: #3A7BFF;
}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus { border-color: #3A7BFF; }
QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {
    background-color: #1E1E28; color: #444455;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    width: 14px; border-left: 1px solid #3A3A4A; border-bottom: 1px solid #3A3A4A;
    background: #22222A; subcontrol-origin: border; subcontrol-position: top right;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 14px; border-left: 1px solid #3A3A4A;
    background: #22222A; subcontrol-origin: border; subcontrol-position: bottom right;
}
QRadioButton, QCheckBox { spacing: 6px; color: #E0E0DC; background: transparent; }
QRadioButton::indicator, QCheckBox::indicator {
    width: 13px; height: 13px; border: 1px solid #3A3A4A; background: #0E0E14;
}
QRadioButton::indicator { border-radius: 7px; }
QRadioButton::indicator:checked, QCheckBox::indicator:checked {
    background: #3A7BFF; border-color: #3A7BFF;
}
QSlider::groove:horizontal { height: 3px; background: #3A3A4A; border-radius: 1px; }
QSlider::handle:horizontal {
    background: #3A7BFF; border: none;
    width: 12px; height: 12px; border-radius: 6px; margin: -5px 0;
}
QSlider::sub-page:horizontal { background: #3A7BFF; border-radius: 1px; }
QScrollBar:vertical { width: 8px; background: #22222A; }
QScrollBar::handle:vertical { background: #3A3A4A; border-radius: 4px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { background-color: #22222A; border-top: 1px solid #3A3A4A; color: #666666; font-size: 10px; }
QToolTip { background-color: #0E0E14; color: #E0E0DC; border: none; padding: 4px 8px; font-size: 10px; }
QSplitter::handle { background: #3A3A4A; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical   { height: 1px; }
QScrollArea { border: none; background: transparent; }
"""
