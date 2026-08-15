"""A title bar that carries the menus, the window name and the window buttons.

A stock QMainWindow spends two rows on chrome before any content: the OS title
bar, then the menu bar under it. This merges them — File/Edit/View/Run/Help sit
in the same strip as the window name and the minimise / maximise / close
buttons — which buys back a row of table.

Not used on macOS. Qt puts a QMenuBar in the system-wide menu bar at the top of
the screen there, so the window never had the extra row to begin with, and a
frameless Mac window would lose its traffic lights for nothing.

Dragging and resizing go through QWindow.startSystemMove/startSystemResize, so
the OS runs its own move and resize loops: Aero Snap, drag-to-edge tiling,
multi-monitor DPI changes and the double-click-to-maximise convention all keep
working without reimplementation. The one Windows 11 affordance this does not
reproduce is the snap-layouts flyout when hovering the maximise button, which
needs the window to answer WM_NCHITTEST with HTMAXBUTTON.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenuBar,
    QSizePolicy,
    QToolButton,
    QWidget,
)

# Width of the invisible band around the window that starts a resize. The
# window keeps a margin this size so the band never sits over a widget — the
# table's scrollbar reaches the window edge, and without the margin its outer
# pixels would resize the window instead of scrolling.
RESIZE_MARGIN = 5


def use_custom_titlebar() -> bool:
    return sys.platform != "darwin"


class WindowButton(QToolButton):
    """One of minimise / maximise / close."""

    def __init__(self, glyph: str, name: str, tooltip: str) -> None:
        super().__init__()
        self.setText(glyph)
        self.setObjectName(name)
        self.setToolTip(tooltip)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.ArrowCursor)
        self.setFixedSize(44, 28)


class TitleBar(QWidget):
    """Menus on the left, window name in the middle, buttons on the right."""

    def __init__(self, window, menu_bar: QMenuBar) -> None:
        super().__init__(window)
        self._window = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(32)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 0, 0)
        lay.setSpacing(0)

        menu_bar.setObjectName("TitleMenuBar")
        # Otherwise the menu bar claims the whole strip and every pixel of it
        # is a menu, leaving nothing to drag the window by.
        menu_bar.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        lay.addWidget(menu_bar)

        lay.addStretch(1)
        self.title = QLabel(window.windowTitle())
        self.title.setObjectName("TitleText")
        self.title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.title)
        lay.addStretch(1)

        self.btn_min = WindowButton("─", "WinMin", "Minimise")
        self.btn_max = WindowButton("□", "WinMax", "Maximise")
        self.btn_close = WindowButton("✕", "WinClose", "Close")
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_max.clicked.connect(self.toggle_maximized)
        self.btn_close.clicked.connect(window.close)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b)

        window.windowTitleChanged.connect(self.title.setText)

    def toggle_maximized(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def sync_maximized(self, maximized: bool) -> None:
        self.btn_max.setText("❐" if maximized else "□")
        self.btn_max.setToolTip("Restore" if maximized else "Maximise")

    # --- dragging ----------------------------------------------------------
    def _draggable(self, pos: QPoint) -> bool:
        child = self.childAt(pos)
        # A press on the menus or the buttons belongs to them, not to the drag.
        return child is None or child is self.title

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._draggable(event.position().toPoint()):
            handle = self._window.windowHandle()
            if handle is not None:
                # Hands the drag to the OS, which is what makes snap work.
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._draggable(event.position().toPoint()):
            self.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


def edges_at(window, pos: QPoint) -> Qt.Edges:
    """Which window edges the point is close enough to drag."""
    if window.isMaximized() or window.isFullScreen():
        return Qt.Edges()
    rect = window.rect()
    edges = Qt.Edges()
    if pos.x() <= RESIZE_MARGIN:
        edges |= Qt.LeftEdge
    elif pos.x() >= rect.width() - RESIZE_MARGIN:
        edges |= Qt.RightEdge
    if pos.y() <= RESIZE_MARGIN:
        edges |= Qt.TopEdge
    elif pos.y() >= rect.height() - RESIZE_MARGIN:
        edges |= Qt.BottomEdge
    return edges


_CURSORS = {
    Qt.LeftEdge: Qt.SizeHorCursor,
    Qt.RightEdge: Qt.SizeHorCursor,
    Qt.TopEdge: Qt.SizeVerCursor,
    Qt.BottomEdge: Qt.SizeVerCursor,
    Qt.LeftEdge | Qt.TopEdge: Qt.SizeFDiagCursor,
    Qt.RightEdge | Qt.BottomEdge: Qt.SizeFDiagCursor,
    Qt.RightEdge | Qt.TopEdge: Qt.SizeBDiagCursor,
    Qt.LeftEdge | Qt.BottomEdge: Qt.SizeBDiagCursor,
}


def cursor_for(edges: Qt.Edges):
    return _CURSORS.get(edges)
