"""COMPAS dark theme.

Palette ported from the plugin-play / hisstory projects so the apps share a
look: dark navy background with deep-orange / golden accents.
"""

from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# --- palette ---------------------------------------------------------------
BACKGROUND = "#12151f"
PANEL_BACKGROUND = "#0b0e17"
# Was #10131d, which is 1.04:1 against PANEL_BACKGROUND — the zebra striping
# was mathematically present and visually absent, and with the grid off that
# left no row separator at all while tracking a value across a wide table.
# #171b28 was the first fix and only reached 1.12:1; this is 1.25:1, which
# survives being composited under a rhythm tint (1.16:1 inside one).
PANEL_ALT = "#1f2436"
GRID_LINE = "#1e2230"
# GRID_LINE is right for a border against a *panel* (menus, tooltips), but at
# 1.15:1 on BACKGROUND it disappeared where it was doing the most work: the
# toolbar separators and the header rules that are the only thing dividing
# twenty-odd columns of bare numbers with the grid switched off.
RULE = "#2c3242"
GRID_TEXT = "#5a5e70"
# Column headers are the only label for twenty-odd columns of bare numbers,
# and the status bar is where all progress and error reporting goes. Both
# used GRID_TEXT at 2.84:1, well under the 4.5:1 readable threshold.
LABEL_TEXT = "#8f95a8"
TEXT_NORMAL = "#b0b4c0"
TEXT_BRIGHT = "#f0f0f0"
ACCENT = "#D96C30"          # deep orange
ACCENT_BRIGHT = "#F3A10F"   # golden orange
ACCENT_DIM = "#8B4420"
BUTTON_SELECTED = "#A34210"
INACTIVE = "#5a5e70"
BUTTON_BG = "#2a2e42"
BUTTON_BG_HOVER = "#353a50"
BUTTON_BORDER = "#343a52"
METRIC_GOOD = "#4CAF50"
METRIC_WARN = "#FF9800"
METRIC_BAD = "#F44336"
# Ticked checkboxes read as neutral state, not as an accent/action, so they
# are gray rather than orange.
CHECK_FILL = "#9aa0b4"
CHECK_BORDER = "#c3c8da"
# The filter box's placeholder is a real instruction ("Filter… (Ctrl+F)"), and
# GRID_TEXT put it at 3.0:1 on the input background — subdued past legible.
PLACEHOLDER_TEXT = "#767c90"

STYLESHEET = f"""
QToolBar {{
    background: {BACKGROUND};
    border: none;
    border-bottom: 1px solid {GRID_LINE};
    padding: 6px;
    spacing: 6px;
}}
QToolBar::separator {{
    background: {RULE};
    width: 1px;
    margin: 4px 6px;
}}
QToolButton {{
    background: {BUTTON_BG};
    color: {TEXT_NORMAL};
    border: 1px solid {BUTTON_BORDER};
    border-radius: 5px;
    padding: 5px 12px;
    font-weight: 600;
}}
QToolButton:hover {{
    background: {BUTTON_BG_HOVER};
    color: {TEXT_BRIGHT};
}}
QToolButton:pressed {{
    background: {BUTTON_SELECTED};
    color: {TEXT_BRIGHT};
}}
QToolButton::menu-indicator {{
    image: none;
}}

QPushButton {{
    background: {BUTTON_BG};
    color: {TEXT_NORMAL};
    border: 1px solid {BUTTON_BORDER};
    border-radius: 5px;
    padding: 5px 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {BUTTON_BG_HOVER};
    color: {TEXT_BRIGHT};
}}
QPushButton:pressed {{
    background: {BUTTON_SELECTED};
    color: {TEXT_BRIGHT};
}}

QPushButton#AnalyzeButton {{
    background: {ACCENT};
    color: #ffffff;
    border: 1px solid {ACCENT_BRIGHT};
    border-radius: 6px;
    padding: 6px 28px;
    font-size: 14px;
    font-weight: bold;
}}
QPushButton#AnalyzeButton:hover {{
    background: {ACCENT_BRIGHT};
    color: {BACKGROUND};
}}
QPushButton#AnalyzeButton:pressed {{
    background: {BUTTON_SELECTED};
    color: {TEXT_BRIGHT};
}}
QPushButton#AnalyzeButton:disabled {{
    background: {ACCENT_DIM};
    border-color: {ACCENT_DIM};
    color: rgba(255, 255, 255, 130);
}}

QTableView {{
    background: {PANEL_BACKGROUND};
    alternate-background-color: {PANEL_ALT};
    gridline-color: {GRID_LINE};
    border: none;
    selection-background-color: {BUTTON_SELECTED};
    selection-color: {TEXT_BRIGHT};
}}
QTableView QTableCornerButton::section {{
    background: {BACKGROUND};
    border: none;
    border-bottom: 1px solid {GRID_LINE};
}}
QHeaderView::section {{
    background: {BACKGROUND};
    color: {LABEL_TEXT};
    border: none;
    border-right: 1px solid {RULE};
    border-bottom: 1px solid {RULE};
    padding: 5px 4px;
    font-weight: 600;
}}
QHeaderView::section:hover {{
    color: {ACCENT_BRIGHT};
}}
/* Header padding was 5px 8px against the style's ~4px cell margin, so a
   right-aligned header sat 4px left of the right-aligned numbers under it. */
QTableView::item {{
    padding: 0px 4px;
}}

QLineEdit {{
    background: {PANEL_BACKGROUND};
    color: {TEXT_NORMAL};
    border: 1px solid {BUTTON_BORDER};
    border-radius: 5px;
    padding: 4px 8px;
    selection-background-color: {BUTTON_SELECTED};
    selection-color: {TEXT_BRIGHT};
}}
QLineEdit:hover {{
    border-color: {RULE};
}}
QLineEdit:focus {{
    border-color: {ACCENT};
    color: {TEXT_BRIGHT};
}}

QComboBox {{
    background: {BUTTON_BG};
    color: {TEXT_NORMAL};
    border: 1px solid {BUTTON_BORDER};
    border-radius: 5px;
    padding: 4px 10px;
}}
QComboBox:hover {{
    background: {BUTTON_BG_HOVER};
    color: {TEXT_BRIGHT};
}}
QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: {BACKGROUND};
    color: {TEXT_NORMAL};
    border: 1px solid {GRID_LINE};
    selection-background-color: {BUTTON_SELECTED};
    selection-color: {TEXT_BRIGHT};
}}

QMenu {{
    background: {BACKGROUND};
    color: {TEXT_NORMAL};
    border: 1px solid {GRID_LINE};
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 24px 5px 12px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {BUTTON_SELECTED};
    color: {TEXT_BRIGHT};
}}
QMenu::separator {{
    height: 1px;
    background: {GRID_LINE};
    margin: 4px 8px;
}}
QMenu::indicator {{
    width: 14px;
    height: 14px;
    margin-left: 6px;
    border: 1px solid {BUTTON_BORDER};
    border-radius: 3px;
    background: {PANEL_BACKGROUND};
}}
QMenu::indicator:checked {{
    background: {CHECK_FILL};
    border-color: {CHECK_BORDER};
}}

QCheckBox {{
    color: {TEXT_NORMAL};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border: 1px solid {BUTTON_BORDER};
    border-radius: 3px;
    background: {PANEL_BACKGROUND};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT_BRIGHT};
}}

QStatusBar {{
    background: {BACKGROUND};
    color: {LABEL_TEXT};
    border-top: 1px solid {GRID_LINE};
}}

QScrollBar:vertical {{
    background: {PANEL_BACKGROUND};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BUTTON_BG_HOVER};
    border-radius: 5px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT_DIM};
}}
QScrollBar:horizontal {{
    background: {PANEL_BACKGROUND};
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BUTTON_BG_HOVER};
    border-radius: 5px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {ACCENT_DIM};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
}}

QDialog, QMessageBox {{
    background: {BACKGROUND};
}}
QLabel {{
    color: {TEXT_NORMAL};
}}
QToolTip {{
    background: #1a1e2c;
    color: {TEXT_NORMAL};
    border: 1px solid {GRID_LINE};
    padding: 4px 6px;
}}
QProgressDialog {{
    background: {BACKGROUND};
}}
QProgressBar {{
    background: {PANEL_BACKGROUND};
    border: 1px solid {GRID_LINE};
    border-radius: 4px;
    color: {TEXT_BRIGHT};
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}

QMenuBar {{
    background: {BACKGROUND};
    color: {TEXT_NORMAL};
    border-bottom: 1px solid {RULE};
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background: {BUTTON_BG_HOVER};
    color: {TEXT_BRIGHT};
}}
QMenuBar::item:pressed {{
    background: {BUTTON_SELECTED};
    color: {TEXT_BRIGHT};
}}

/* Declaring an explicit border on a button sends Qt down the
   non-native-border path, and Fusion's focus rect is then never drawn — so
   tabbing between Analyze / Stop / Columns / Facets / OK gave no feedback. */
QPushButton:focus, QToolButton:focus, QCheckBox:focus {{
    border-color: {ACCENT_BRIGHT};
}}
QPushButton:default {{
    border-color: {ACCENT};
}}

/* An *unqualified* `color`/`background` in a stylesheet also claims the
   QPalette::Disabled group, which overrides the disabled colours set in
   apply_theme — so without these every greyed-out widget rendered
   pixel-identical to a live one. AnalyzeButton had its own :disabled rule
   and was the only thing in the app that visibly greyed out. */
QPushButton:disabled, QToolButton:disabled {{
    background: #1c2030;
    color: {INACTIVE};
    border-color: #262b3c;
}}
QCheckBox:disabled {{
    color: {INACTIVE};
}}
QCheckBox:disabled::indicator {{
    border-color: #262b3c;
    background: {BACKGROUND};
}}
QComboBox:disabled {{
    background: #1c2030;
    color: {INACTIVE};
    border-color: #262b3c;
}}
QMenu::item:disabled {{
    color: #6b7080;
}}
"""


def apply_theme(app: QApplication) -> None:
    """Fusion style + dark palette + stylesheet, applied app-wide."""
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BACKGROUND))
    pal.setColor(QPalette.WindowText, QColor(TEXT_NORMAL))
    pal.setColor(QPalette.Base, QColor(PANEL_BACKGROUND))
    pal.setColor(QPalette.AlternateBase, QColor(PANEL_ALT))
    pal.setColor(QPalette.Text, QColor(TEXT_NORMAL))
    pal.setColor(QPalette.BrightText, QColor(TEXT_BRIGHT))
    pal.setColor(QPalette.Button, QColor(BUTTON_BG))
    pal.setColor(QPalette.ButtonText, QColor(TEXT_NORMAL))
    pal.setColor(QPalette.Highlight, QColor(BUTTON_SELECTED))
    pal.setColor(QPalette.HighlightedText, QColor(TEXT_BRIGHT))
    pal.setColor(QPalette.ToolTipBase, QColor("#1a1e2c"))
    pal.setColor(QPalette.ToolTipText, QColor(TEXT_NORMAL))
    pal.setColor(QPalette.Link, QColor(ACCENT_BRIGHT))
    pal.setColor(QPalette.PlaceholderText, QColor(PLACEHOLDER_TEXT))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(INACTIVE))
    app.setPalette(pal)

    app.setStyleSheet(STYLESHEET)


def apply_dark_title_bar(window) -> None:
    """Ask DWM to draw the native title bar dark so it matches the theme.

    Call after the window is shown (it needs a native handle). No-op off
    Windows; harmless if the call fails on older Windows builds.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            int(window.winId()), DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass
