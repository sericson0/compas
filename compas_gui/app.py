"""COMPAS GUI — main window.

Run with:  python -m compas_gui
"""

from __future__ import annotations

import csv
import html
import json
import sys
from collections import deque
from pathlib import Path

from PySide6.QtCore import (
    QElapsedTimer,
    QRect,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
)
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QGuiApplication,
    QKeySequence,
    QPainter,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QTableView,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QVBoxLayout,
)

from compas_core import facets
from compas_gui import session, theme
from compas_gui.model import (
    COLUMN_TOOLTIPS,
    TrackRow,
    TrackSortProxy,
    TrackTableModel,
)
from compas_gui.workers import (
    AnalyzeTask,
    LibrosaWarmup,
    ScanSignals,
    ScanTask,
    WorkerSignals,
    suggested_thread_count,
)

AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".aiff", ".wma"}
RHYTHM_CHOICES = ["auto", "tango", "vals", "milonga"]

# Everything else is toggleable. File stays because hiding it would leave a
# table of rows you cannot tell apart.
ALWAYS_VISIBLE_COLUMNS = {"File"}

# Shown on first run only — after that the Columns menu's choice is what
# persists. "Nothing hidden" is not a neutral default but the densest possible
# one: 23 columns want ~2800px, so in a default window two thirds of the table
# including Status and Facets started off the right edge. These seven are the
# secondary and diagnostic ones — comparison values, loudness detail, and
# Harmony, whose own tooltip opens "PROVISIONAL". All are one tick away.
DEFAULT_HIDDEN_COLUMNS = {
    "BPM range", "Bars/min", "Camelot", "Tag BPM/key",
    "LUFS", "LRA (LU)", "Harmony",
}

VOCABULARY_LABELS = {facets.ENGLISH: "English", facets.TANGO: "Tango"}


class StayOpenMenu(QMenu):
    """A menu that stays open when a checkable item is toggled, so users
    can tick several columns without reopening it each time."""

    def mouseReleaseEvent(self, event) -> None:
        action = self.activeAction()
        if action is not None and action.isCheckable() and action.isEnabled():
            action.trigger()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class TrackTable(QTableView):
    """The results table, plus a first-run message on the empty viewport.

    An empty QTableView is an undifferentiated dark rectangle, and the only
    thing that told a new user what to do was one line in the status bar at
    the very bottom of the window.
    """

    placeholder = ("Drop tango files or folders anywhere in this window\n\n"
                   "or  File ▸ Add files…  (Ctrl+O)\n"
                   "then press  ▶ Analyze  (Ctrl+Return)")

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        model = self.model()
        if model is not None and model.rowCount() > 0:
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor(theme.LABEL_TEXT))
        font = painter.font()
        font.setPointSizeF(font.pointSizeF() + 1.5)
        painter.setFont(font)
        painter.drawText(self.viewport().rect(),
                         Qt.AlignCenter | Qt.TextWordWrap, self.placeholder)
        painter.end()


def _is_audio(p: Path) -> bool:
    # "._name.m4a" is a macOS AppleDouble resource fork: right extension,
    # no audio inside. A library copied from a Mac is full of them.
    return p.suffix.lower() in AUDIO_EXTS and not p.name.startswith("._")


def collect_audio_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if _is_audio(f)))
        elif p.is_file() and _is_audio(p):
            files.append(p)
    return files


class WriteTagsDialog(QDialog):
    """Options for writing analysis results into file tags."""

    def __init__(self, parent, rows: list[TrackRow], settings: QSettings,
                 *, scoped_to_selection: bool = False,
                 axis_keys=(), vocabulary: str = facets.ENGLISH) -> None:
        super().__init__(parent)
        self.setWindowTitle("Write tags")
        lay = QVBoxLayout(self)

        # This modifies files on disk in place. A bare count could not tell
        # "3 selected" from "3 in the list", so name the scope and the files.
        scope = (f"the {len(rows)} selected track(s)" if scoped_to_selection
                 else f"all {len(rows)} analyzed track(s)")
        heading = QLabel(f"Write analysis results into the tags of {scope}.\n"
                         "Existing tag fields not listed below are left "
                         "untouched.")
        heading.setWordWrap(True)
        lay.addWidget(heading)

        names = [r.path.name for r in rows[:4]]
        if len(rows) > len(names):
            names.append(f"… and {len(rows) - len(names)} more")
        listing = QLabel("  " + "\n  ".join(names))
        listing.setStyleSheet(f"color: {theme.LABEL_TEXT};")
        lay.addWidget(listing)

        n_bpm = sum(1 for r in rows if r.analysis.tag_bpm)
        n_key = sum(1 for r in rows if r.analysis.tag_key)

        self.cb_bpm = QCheckBox("BPM (standard tag — VirtualDJ reads this)")
        self.cb_key = QCheckBox("Initial key (standard tag)")
        # These two are the only fields that overwrite something another tool
        # wrote. COMPAS_* are its own namespace and cannot collide.
        if n_bpm:
            self.cb_bpm.setText(
                self.cb_bpm.text()
                + f" — replaces an existing BPM tag on {n_bpm} file(s)")
        if n_key:
            self.cb_key.setText(
                self.cb_key.text()
                + f" — replaces an existing key tag on {n_key} file(s)")
        self.cb_compas = QCheckBox(
            "COMPAS_* fields (energy, drive, articulation, texture, "
            "harmony, stability, timing, BPM range…)")
        self.cb_facets = QCheckBox(
            "COMPAS_FACETS — the composed phrase, in the vocabulary and "
            "axes currently selected")
        if axis_keys and rows:
            example = facets.label(rows[0].analysis, vocabulary, axis_keys)
            if example:
                self.cb_facets.setText(
                    self.cb_facets.text() + f'\n(e.g. "{example}")')
        self.cb_comment = QCheckBox(
            "Append \"COMPAS Energy N\" to the comment "
            "(keeps existing comment text)")
        self.cb_bpm.setChecked(settings.value("tags/bpm", True, bool))
        self.cb_key.setChecked(settings.value("tags/key", True, bool))
        self.cb_compas.setChecked(settings.value("tags/compas", True, bool))
        self.cb_facets.setChecked(settings.value("tags/facets", True, bool))
        self.cb_comment.setChecked(settings.value("tags/comment", False, bool))
        # With no axes ticked in the Facets menu the composed phrase is the
        # empty string, and writing it stored a blank COMPAS_FACETS in every
        # file — worse than not writing the field at all.
        self._has_axes = bool(axis_keys)
        self._sync_facets_enabled()
        self.cb_compas.toggled.connect(
            lambda _on: self._sync_facets_enabled())
        if not self._has_axes:
            self.cb_facets.setToolTip(
                "No axes are selected in the Facets menu, so the composed "
                "phrase would be empty.")

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Key format:"))
        self.key_format = QComboBox()
        self.key_format.addItems(["standard (Dm)", "camelot (7A)"])
        if settings.value("tags/key_format", "standard") == "camelot":
            self.key_format.setCurrentIndex(1)
        fmt_row.addWidget(self.key_format)
        fmt_row.addStretch(1)

        for w in (self.cb_bpm, self.cb_key, self.cb_compas, self.cb_facets,
                  self.cb_comment):
            lay.addWidget(w)
        lay.addLayout(fmt_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._ok = buttons.button(QDialogButtonBox.Ok)
        self._ok.setText("Write tags")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        # With every box unticked write_tags selects no fields and returns
        # without saving, while the status bar still reported "Tags written
        # for N file(s)".
        for cb in (self.cb_bpm, self.cb_key, self.cb_compas, self.cb_comment):
            cb.toggled.connect(lambda _on: self._sync_ok())
        self._sync_ok()

    def _sync_facets_enabled(self) -> None:
        self.cb_facets.setEnabled(self.cb_compas.isChecked()
                                  and self._has_axes)

    def _sync_ok(self) -> None:
        self._ok.setEnabled(any(cb.isChecked() for cb in (
            self.cb_bpm, self.cb_key, self.cb_compas, self.cb_comment)))

    def options(self) -> dict:
        return {
            "bpm": self.cb_bpm.isChecked(),
            "key": self.cb_key.isChecked(),
            "compas": self.cb_compas.isChecked(),
            "facets": self.cb_facets.isChecked() and self.cb_facets.isEnabled(),
            "comment": self.cb_comment.isChecked(),
            "camelot": self.key_format.currentIndex() == 1,
        }


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("COMPAS — Tango Music Analyzer")
        # First-run size only; restored geometry wins below. The default
        # column set measures ~1840px, so ask for that much and clamp to the
        # screen — on a 1080p display every default column is then visible
        # without scrolling, which 1240 was never close to.
        screen = QGuiApplication.primaryScreen()
        available = (screen.availableGeometry() if screen is not None
                     else QRect(0, 0, 1840, 820))
        # max() floors it: a headless or misreported screen must not produce a
        # window too small to show the toolbar.
        self.resize(max(1000, min(1840, available.width() - 60)),
                    max(600, min(820, available.height() - 80)))
        self.setAcceptDrops(True)
        self.settings = QSettings("compas", "compas")

        self.model = TrackTableModel(self._facet_axes(), self._vocabulary())
        self.proxy = TrackSortProxy(self)
        self.proxy.setSourceModel(self.model)

        self.table = TrackTable()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        # setSortingEnabled adopts the header's default indicator, which is
        # descending — the table would open sorted Z→A with a sort arrow the
        # user never clicked.
        self.table.sortByColumn(0, Qt.AscendingOrder)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        # Wrapping is on by default, and with a one-line row height that
        # clips rather than elides — so a long filename or error lost the "…"
        # that says there is more text.
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        # Row numbers mean nothing in a sortable table, and cost ~40px of a
        # viewport that is already short of room.
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionsMovable(True)
        header.setMinimumSectionSize(44)
        header.setDefaultSectionSize(64)
        self.setCentralWidget(self.table)

        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(suggested_thread_count())
        self.pool.start(LibrosaWarmup())

        # Its own pool: a scan queued behind four long analysis tasks on the
        # global pool would not start until the batch finished, so dropping a
        # folder mid-run would appear to do nothing for minutes.
        self.scan_pool = QThreadPool()
        self.scan_pool.setMaxThreadCount(1)
        self.scan_signals = ScanSignals()
        self.scan_signals.scanned.connect(self._on_scanned)
        self.scan_generation = 0
        self._scans_running = 0

        self.signals = WorkerSignals()
        self.signals.started.connect(self._on_started)
        self.signals.done.connect(self._on_done)
        self.signals.failed.connect(self._on_failed)
        self.generation = 0
        self._pending = 0

        # Throughput for the ETA: the elapsed-ms stamp of each completion,
        # most recent last. A rate is completions per second, which already
        # accounts for the worker count — timing one track and dividing would
        # not. Windowed rather than cumulative because the first few tracks
        # pay numba's JIT warmup and would otherwise inflate the estimate for
        # the rest of the run.
        self._run_timer = QElapsedTimer()
        self._completions: deque[int] = deque(maxlen=24)

        # Autosave is debounced: a 500-track run completes a row every second
        # or so, and rewriting the whole session each time would be pointless
        # disk churn.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(2500)
        self._save_timer.timeout.connect(self._save_session)

        self._build_toolbar()
        self._columns_fitted = False
        self._apply_column_visibility()
        geometry = self.settings.value("win/geometry", None)
        if geometry:
            self.restoreGeometry(geometry)
        self._restore_header()
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self._sync_actions())
        self._sync_actions()
        self.statusBar().showMessage(
            "Drop files or folders anywhere in the window (or File ▸ Add "
            "files, Ctrl+O), then press Analyze.")
        # Last, so its status message is the one left on screen.
        self._restore_session()

    # --- UI scaffolding -------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        act_files = QAction("Add files…", self)
        act_files.triggered.connect(self._add_files)
        tb.addAction(act_files)

        # Add folder and Write tags are File-menu only: the toolbar has to
        # fit the default 1240px window, and Columns/Facets losing that race
        # is what buried them behind an overflow chevron.
        act_folder = QAction("Add folder…", self)
        act_folder.triggered.connect(self._add_folder)

        tb.addSeparator()
        tb.addWidget(QLabel(" Rhythm: "))
        self.rhythm_combo = QComboBox()
        self.rhythm_combo.addItems(RHYTHM_CHOICES)
        self.rhythm_combo.setToolTip(
            "auto = use the GENRE tag, then an audio heuristic.\n"
            "Or force tango / vals / milonga for everything you analyze.")
        tb.addWidget(self.rhythm_combo)
        tb.addSeparator()

        self.fast_check = QCheckBox("Fast")
        self.fast_check.setToolTip(
            "Skip harmonic/percussive separation — roughly 4× faster on a "
            "big batch.\n"
            "Only the Key and Camelot columns are affected: everything else "
            "(BPM, stability, drive, energy, loudness) comes out identical.\n"
            "On the example corpus 3 tracks of 19 got a different key, with "
            "no net accuracy loss against their Mixed In Key tags.")
        self.fast_check.setChecked(self.settings.value("analysis/fast", False, bool))
        self.fast_check.toggled.connect(
            lambda on: self.settings.setValue("analysis/fast", on))
        tb.addWidget(self.fast_check)
        tb.addSeparator()

        self.btn_analyze = QPushButton("▶  Analyze")
        self.btn_analyze.setObjectName("AnalyzeButton")
        self.btn_analyze.setCursor(Qt.PointingHandCursor)
        self.btn_analyze.setToolTip(
            "Analyze every pending track, and retry any that failed "
            "(Ctrl+Return).\n"
            "Tracks already analyzed are re-run only if you changed Rhythm "
            "or Fast since.")
        # The shortcut lives on the Run menu action; setting it here too
        # makes it ambiguous and neither fires.
        self.btn_analyze.clicked.connect(self._analyze_pending)
        tb.addWidget(self.btn_analyze)

        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setToolTip(
            "Stop the run (Esc). Tracks already analyzed keep their results; "
            "the rest go back to pending.")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        tb.addWidget(self.btn_stop)

        self.act_tags = QAction("Write tags…", self)
        self.act_tags.triggered.connect(self._write_tags)
        self.act_csv = QAction("Export CSV…", self)
        self.act_csv.triggered.connect(lambda: self._export("csv"))
        self.act_json = QAction("Export JSON…", self)
        self.act_json.triggered.connect(lambda: self._export("json"))

        tb.addSeparator()
        # Write tags is the payoff and step 1 of the VirtualDJ workflow, and
        # it was File-menu-only on width grounds that no longer hold — the
        # toolbar carries seven compact items now, not the ten that forced
        # Columns and Facets behind an overflow chevron.
        btn_output = QToolButton()
        btn_output.setText("Output ▾")
        btn_output.setToolTip(
            "Write results into the files' tags, or export the table.")
        btn_output.setPopupMode(QToolButton.InstantPopup)
        output_menu = QMenu(self)
        output_menu.addAction(self.act_tags)
        output_menu.addSeparator()
        output_menu.addAction(self.act_csv)
        output_menu.addAction(self.act_json)
        btn_output.setMenu(output_menu)
        tb.addWidget(btn_output)

        tb.addSeparator()
        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Filter… (Ctrl+F)")
        self.filter_box.setClearButtonEnabled(True)
        self.filter_box.setMaximumWidth(200)
        self.filter_box.setToolTip(
            "Show only tracks matching this text.\n"
            "Matches the filename, rhythm, key, status, the facet readings "
            "and any error message — so \"milonga\", \"Dm\", \"driving\" or "
            "\"ffmpeg\" all work.\n"
            "Filtering never changes what Analyze or Write tags act on.")
        self.filter_box.textChanged.connect(self._on_filter_changed)
        tb.addWidget(self.filter_box)

        tb.addSeparator()
        self.btn_columns = QToolButton()
        self.btn_columns.setText("Columns ▾")
        self.btn_columns.setToolTip(
            "Show or hide any column in the table, metric or facet.\n"
            "The choice is remembered between sessions.")
        self.btn_columns.setPopupMode(QToolButton.InstantPopup)
        self.btn_columns.setMenu(self._build_columns_menu())
        tb.addWidget(self.btn_columns)

        btn_facets = QToolButton()
        btn_facets.setText("Facets ▾")
        btn_facets.setToolTip(
            "Describe each track in words instead of numbers.\n"
            "Tick the axes you want to compare over: each adds a ≡ column, "
            "and the Facets column composes them into a phrase.\n"
            "Nothing here is a new measurement — a facet is a threshold over "
            "a column you already have.")
        btn_facets.setPopupMode(QToolButton.InstantPopup)
        self.facets_menu = self._build_facets_menu()
        btn_facets.setMenu(self.facets_menu)
        tb.addWidget(btn_facets)

        # A status-bar string that changes every few seconds is the one widget
        # in the window least likely to catch the eye; on a 500-track run the
        # question is "is this stuck?", and a bar answers it at a glance.
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(220)
        self.progress_bar.setMaximumHeight(14)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self._build_menu_bar(act_files, act_folder)

    def _build_menu_bar(self, act_files, act_folder) -> None:
        """Everything reachable from the keyboard, and nothing that can be
        pushed off the end of the toolbar.

        The toolbar used to carry Add/Rhythm/Fast/Analyze/Write tags/Export
        CSV/Export JSON/Columns/Facets/Clear, which wants ~1990 px. The
        window opens at 1240 and a 1080p screen is 1920, so Columns and
        Facets — the two menus this app is built around — spent their life
        collapsed behind an unlabelled overflow chevron.
        """
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        act_files.setShortcut(QKeySequence.Open)
        file_menu.addAction(act_files)
        act_folder.setShortcut(QKeySequence("Ctrl+Shift+O"))
        file_menu.addAction(act_folder)
        file_menu.addSeparator()
        self.act_tags.setShortcut(QKeySequence("Ctrl+T"))
        file_menu.addAction(self.act_tags)
        file_menu.addSeparator()
        self.act_csv.setShortcut(QKeySequence("Ctrl+E"))
        file_menu.addAction(self.act_csv)
        file_menu.addAction(self.act_json)

        edit_menu = bar.addMenu("&Edit")
        self.act_remove = QAction("Remove selected from list", self)
        self.act_remove.setShortcut(QKeySequence.Delete)
        self.act_remove.setShortcutContext(Qt.WidgetShortcut)
        self.act_remove.triggered.connect(
            lambda: self._remove_rows(self._selected_source_rows()))
        self.table.addAction(self.act_remove)
        edit_menu.addAction(self.act_remove)

        self.act_clear = QAction("Clear all", self)
        self.act_clear.triggered.connect(self._clear)
        edit_menu.addAction(self.act_clear)

        view_menu = bar.addMenu("&View")
        act_find = QAction("Filter tracks…", self)
        act_find.setShortcut(QKeySequence.Find)
        act_find.triggered.connect(self._focus_filter)
        view_menu.addAction(act_find)
        self.act_failed_only = QAction("Show only failed tracks", self)
        self.act_failed_only.setCheckable(True)
        self.act_failed_only.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.act_failed_only.toggled.connect(self._on_failed_only)
        view_menu.addAction(self.act_failed_only)
        view_menu.addSeparator()
        act_clear_filter = QAction("Clear filters", self)
        act_clear_filter.setShortcut(QKeySequence("Ctrl+Shift+X"))
        act_clear_filter.triggered.connect(self._clear_filters)
        view_menu.addAction(act_clear_filter)

        run_menu = bar.addMenu("&Run")
        self.act_analyze = QAction("Analyze pending", self)
        self.act_analyze.setShortcut(QKeySequence("Ctrl+Return"))
        self.act_analyze.triggered.connect(self._analyze_pending)
        run_menu.addAction(self.act_analyze)
        self.act_stop = QAction("Stop", self)
        self.act_stop.setShortcut(QKeySequence("Esc"))
        self.act_stop.setEnabled(False)
        self.act_stop.triggered.connect(self._stop)
        run_menu.addAction(self.act_stop)

        help_menu = bar.addMenu("&Help")
        act_columns_ref = QAction("What the columns mean…", self)
        act_columns_ref.setShortcut(QKeySequence.HelpContents)
        act_columns_ref.triggered.connect(self._show_column_reference)
        help_menu.addAction(act_columns_ref)
        act_about = QAction("About COMPAS", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    # --- session persistence ------------------------------------------------
    def _save_soon(self) -> None:
        """Queue an autosave; repeated calls coalesce into one write."""
        self._save_timer.start()

    def _save_session(self) -> None:
        self._save_timer.stop()
        session.save(self.model.rows)

    def _restore_session(self) -> None:
        """Bring back the last session's tracks and results.

        Restored without asking: the alternative is a modal on every launch,
        and Clear all is one keystroke away if the list is unwanted. Rows that
        were mid-flight come back as pending — session.py drops their status,
        not their place in the list.
        """
        rows = session.load()
        if not rows:
            return
        self.model.beginResetModel()
        self.model.rows = rows
        self.model.endResetModel()
        analyzed = sum(1 for r in rows if r.analysis is not None)
        failed = sum(1 for r in rows if r.status == "error")
        self._fit_columns()
        self._columns_fitted = True
        self._update_progress()
        bits = [f"{len(rows)} track(s)"]
        if analyzed:
            bits.append(f"{analyzed} with results")
        if failed:
            bits.append(f"{failed} failed")
        pending = len(rows) - analyzed - failed
        tail = (" Press Analyze for the remaining "
                f"{pending}." if pending else "")
        self.statusBar().showMessage(
            "Restored your last session — " + ", ".join(bits) + "." + tail)

    # --- filtering ----------------------------------------------------------
    def _focus_filter(self) -> None:
        self.filter_box.setFocus(Qt.ShortcutFocusReason)
        self.filter_box.selectAll()

    def _on_filter_changed(self, text: str) -> None:
        self.proxy.set_needle(text)
        self._report_filter()

    def _on_failed_only(self, on: bool) -> None:
        self.proxy.set_failed_only(on)
        self._report_filter()

    def _clear_filters(self) -> None:
        self.filter_box.clear()
        self.act_failed_only.setChecked(False)

    def _report_filter(self) -> None:
        """Say how much of the list is hidden.

        A filter that hides 480 of 500 rows looks exactly like a list that
        only ever had 20 in it, and the difference matters before pressing
        Analyze — which acts on everything, filtered or not.
        """
        total = len(self.model.rows)
        if not self.proxy.is_filtered():
            self._update_progress()
            return
        shown = self.proxy.rowCount()
        bits = []
        if self.act_failed_only.isChecked():
            bits.append("failed only")
        if self.filter_box.text().strip():
            bits.append(f'matching "{self.filter_box.text().strip()}"')
        self.statusBar().showMessage(
            f"Showing {shown} of {total} track(s) — {', '.join(bits)}. "
            "Analyze and Write tags still act on the whole list.")

    # --- geometry and column widths ---------------------------------------
    FILE_COLUMN_WIDTH = 340

    def _header_key(self) -> str:
        """Header state is stored per facet-axis selection.

        QHeaderView.saveState is index-based, so restoring a 23-column layout
        into a 20-column table shifts every width one to the left. The axis
        selection is the only thing that changes the column count.
        """
        return "table/header/" + ",".join(self.model.axis_keys)

    def _fit_columns(self) -> None:
        """Size columns to their contents, then re-assert the File column.

        Only column 0 was ever sized, leaving the other 22 at Qt's 100px
        default: 2540px of table in a 1240px window, so the app always opened
        with a horizontal scrollbar, stretchLastSection never fired, and
        Status and Facets — where progress and the payoff live — sat ~1200px
        off the right edge. Sections stay Interactive, so this is a starting
        point the user can still drag.
        """
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, self.FILE_COLUMN_WIDTH)

    def _save_layout(self) -> None:
        self.settings.setValue("win/geometry", self.saveGeometry())
        self.settings.setValue(
            self._header_key(), self.table.horizontalHeader().saveState())

    def _restore_header(self) -> None:
        """Restore saved column widths and order for the current axis set.

        Runs after _apply_column_visibility, because the saved state carries
        hidden-ness too and would otherwise fight the columns/hidden setting.
        """
        state = self.settings.value(self._header_key(), None)
        if state:
            self.table.horizontalHeader().restoreState(state)
            self._columns_fitted = True
        else:
            self._fit_columns()
            # Header text is all there is to measure before any rows exist, so
            # re-fit once real filenames and numbers land.
            self._columns_fitted = bool(self.model.rows)
        self._apply_column_visibility()

    # --- column visibility ------------------------------------------------
    def _hidden_columns(self) -> set[str]:
        # contains(), not a None default: QSettings.value(key, None, str)
        # returns "" for a missing key, so "never set" and "set to empty"
        # are indistinguishable that way — and they mean opposite things
        # here. An existing user who ticked every column on stores "[]".
        if not self.settings.contains("columns/hidden"):
            return set(DEFAULT_HIDDEN_COLUMNS)
        try:
            hidden = set(json.loads(
                self.settings.value("columns/hidden", "[]", str)))
        except (TypeError, ValueError):
            hidden = set()
        return hidden - ALWAYS_VISIBLE_COLUMNS

    def _build_columns_menu(self) -> QMenu:
        """Every column in the table, metric and facet alike.

        Facet columns come and go with the Facets menu, so this is rebuilt
        whenever that selection changes — and the toggles key on the header
        name rather than a column index, which would go stale the moment a
        facet column was inserted before it.
        """
        menu = StayOpenMenu(self)
        menu.setToolTipsVisible(True)
        hidden = self._hidden_columns()

        metric = [c for c in self.model.columns if not c.facet]
        facet = [c for c in self.model.columns if c.facet]
        for group, label in ((metric, None), (facet, "Facet columns")):
            if not group:
                continue
            if label:
                # addSection renders a real heading. A disabled action reads
                # as "unavailable option" and draws in the disabled colour,
                # which is the one the theme calls unreadable.
                menu.addSection(label)
            for column in group:
                act = QAction(column.header, menu)
                act.setToolTip(column.tooltip
                               or COLUMN_TOOLTIPS.get(column.header, ""))
                act.setCheckable(True)
                act.setChecked(column.header not in hidden)
                if column.header in ALWAYS_VISIBLE_COLUMNS:
                    # Hiding the filename would leave rows unidentifiable.
                    act.setEnabled(False)
                    act.setToolTip(f"{column.header} is always shown — "
                                   "it is what identifies the row.")
                act.toggled.connect(
                    lambda shown, h=column.header: self._set_column_shown(
                        h, shown))
                menu.addAction(act)
        return menu

    def _rebuild_columns_menu(self) -> None:
        # QToolButton.setMenu does not adopt or delete the old menu, and it
        # was parented to this window, so without deleteLater every facet
        # toggle leaks a menu and its ~22 actions for the session.
        old = self.btn_columns.menu()
        self.btn_columns.setMenu(self._build_columns_menu())
        if old is not None:
            old.deleteLater()

    def _column_index(self, header: str) -> int | None:
        for i, column in enumerate(self.model.columns):
            if column.header == header:
                return i
        return None

    def _set_column_shown(self, header: str, shown: bool) -> None:
        col = self._column_index(header)
        if col is not None:
            self.table.setColumnHidden(col, not shown)
        hidden = self._hidden_columns()
        if shown:
            hidden.discard(header)
        else:
            hidden.add(header)
        self.settings.setValue("columns/hidden", json.dumps(sorted(hidden)))

    def _apply_column_visibility(self) -> None:
        hidden = self._hidden_columns()
        for col, column in enumerate(self.model.columns):
            self.table.setColumnHidden(col, column.header in hidden)

    # --- facets -----------------------------------------------------------
    def _facet_axes(self) -> tuple[str, ...]:
        """Selected axis keys, filtered against the axes that exist."""
        # See _hidden_columns: a missing key reads back as "", not None, so
        # this has to ask contains() to tell "unset" from "none selected".
        if not self.settings.contains("facets/axes"):
            return facets.DEFAULT_AXIS_KEYS
        try:
            keys = json.loads(self.settings.value("facets/axes", "[]", str))
        except (TypeError, ValueError):
            return facets.DEFAULT_AXIS_KEYS
        return tuple(k for k in keys if k in facets.AXES_BY_KEY)

    def _vocabulary(self) -> str:
        value = self.settings.value("facets/vocabulary", facets.ENGLISH, str)
        return value if value in facets.VOCABULARIES else facets.ENGLISH

    def _build_facets_menu(self) -> QMenu:
        menu = StayOpenMenu(self)
        menu.setToolTipsVisible(True)

        vocabulary = self._vocabulary()
        menu.addSection("Vocabulary")
        # An exclusive QActionGroup refuses to un-check the current member.
        # Without it, clicking the already-selected vocabulary un-checked it
        # and nothing re-checked anything, leaving a menu that claimed no
        # vocabulary was selected while the table kept rendering one.
        self._vocab_group = QActionGroup(menu)
        self._vocab_group.setExclusive(True)
        for name in facets.VOCABULARIES:
            # Indentation used to be literal spaces in the action text, which
            # is also its type-ahead key — so typing "T" for Tango missed.
            act = QAction(VOCABULARY_LABELS[name], menu)
            act.setCheckable(True)
            act.setChecked(name == vocabulary)
            act.setToolTip(
                "Words for the same thresholds: "
                + ", ".join(a.labels[name][-1] for a in facets.AXES[:4]) + "…")
            act.triggered.connect(lambda _checked, v=name:
                                  self._set_vocabulary(v))
            self._vocab_group.addAction(act)
            menu.addAction(act)

        menu.addSection("Axes to compare over")
        selected = set(self._facet_axes())
        for axis in facets.AXES:
            act = QAction(axis.name, menu)
            act.setCheckable(True)
            act.setChecked(axis.key in selected)
            act.setToolTip(COLUMN_TOOLTIPS.get(axis.name) or axis.help)
            act.toggled.connect(
                lambda on, k=axis.key: self._set_axis_selected(k, on))
            menu.addAction(act)
        return menu

    def _set_vocabulary(self, vocabulary: str) -> None:
        if vocabulary == self.model.vocabulary:
            return
        self.settings.setValue("facets/vocabulary", vocabulary)
        self._rebuild_facet_columns(self.model.axis_keys, vocabulary)

    def _set_axis_selected(self, key: str, selected: bool) -> None:
        keys = [a.key for a in facets.AXES
                if (a.key in self.model.axis_keys or a.key == key)
                and (a.key != key or selected)]
        self.settings.setValue("facets/axes", json.dumps(keys))
        self._rebuild_facet_columns(keys, self.model.vocabulary)

    def _rebuild_facet_columns(self, axis_keys, vocabulary: str) -> None:
        # A model reset drops per-column state, so re-apply what the view
        # owns: hidden columns and the column widths. The Columns menu lists
        # facet columns too, so it has to be rebuilt alongside them.
        self._save_layout()          # keep the outgoing axis set's widths
        self.model.set_facets(axis_keys, vocabulary)
        self._apply_column_visibility()
        self._restore_header()
        self._rebuild_columns_menu()
        self._sync_actions()

    # --- adding files ----------------------------------------------------
    @staticmethod
    def _droppable(mime) -> list[Path]:
        """Local files and folders in a drag that COMPAS could actually add."""
        paths = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            p = Path(url.toLocalFile())
            if p.is_dir() or _is_audio(p):
                paths.append(p)
        return paths

    def dragEnterEvent(self, event) -> None:
        # Accepting anything with URLs gave the OS "drop here" cursor to a
        # link dragged out of a browser, and the drop then did nothing at all.
        if event.mimeData().hasUrls() and self._droppable(event.mimeData()):
            event.acceptProposedAction()
            self.statusBar().showMessage("Drop to add these to the list…")

    def dragLeaveEvent(self, event) -> None:
        self._update_progress()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        # toLocalFile() returns "" for a non-local URL (a link dragged from a
        # browser, say) and Path("") is WindowsPath('.'), which is a
        # directory — so an unfiltered drop used to rglob the whole working
        # directory. _droppable is the same filter dragEnterEvent accepts on.
        paths = self._droppable(event.mimeData())
        event.acceptProposedAction()
        if not paths:
            self.statusBar().showMessage(
                "Nothing usable in that drop — COMPAS takes local audio "
                "files and folders.")
            return
        self._add_paths(paths)

    def _add_files(self) -> None:
        exts = " ".join(f"*{e}" for e in sorted(AUDIO_EXTS))
        names, _ = QFileDialog.getOpenFileNames(
            self, "Add audio files", "", f"Audio files ({exts})")
        self._add_paths([Path(n) for n in names])

    def _add_folder(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "Add folder")
        if name:
            self._add_paths([Path(name)])

    def _add_paths(self, paths: list[Path]) -> None:
        if not paths:
            # Also reached by cancelling the file dialog, where a complaint
            # would be wrong — dropEvent reports its own empty case.
            return
        # Handed to a worker: rglob over a library is far too slow to run on
        # the UI thread. Results arrive at _on_scanned.
        self._scans_running += 1
        self.statusBar().showMessage("Scanning for audio files…")
        self._update_progress()
        self.scan_pool.start(ScanTask(
            self.scan_generation, list(paths), collect_audio_files,
            self.scan_signals))

    def _on_scanned(self, generation: int, files: list[Path]) -> None:
        self._scans_running = max(0, self._scans_running - 1)
        if generation != self.scan_generation:
            # Cleared or reset while the scan was walking the tree.
            self._update_progress()
            return
        if files:
            before = len(self.model.rows)
            self.model.add_paths(files)
            added = len(self.model.rows) - before
            if not self._columns_fitted and self.model.rows:
                # Before any rows existed there was nothing but header text to
                # measure, so this is the first honest fit.
                self._fit_columns()
                self._columns_fitted = True
            skipped = len(files) - added
            note = f" ({skipped} already in the list)" if skipped else ""
            if not added:
                self._update_progress()
                self.statusBar().showMessage(
                    f"All {skipped} file(s) were already in the list.")
            elif self._pending:
                # Analyze is disabled during a run, so telling the user to
                # press it would be a dead end. New rows are appended, which
                # leaves every in-flight row index valid, so they can just
                # join the batch.
                self._queue_rows(range(before, before + added))
                self.statusBar().showMessage(
                    f"{added} file(s) added{note} — joined the running batch.")
            else:
                self._update_progress()
                self.statusBar().showMessage(
                    f"{added} file(s) added{note} — "
                    f"{len(self.model.rows)} in the list. Press Analyze.")
            if added:
                self._save_soon()
        else:
            self._update_progress()
            self.statusBar().showMessage(
                "No audio files found in what you added.")

    # --- analysis --------------------------------------------------------
    def _fast_mode(self) -> bool:
        return self.fast_check.isChecked()

    def _analyze_pending(self) -> None:
        rhythm = self.rhythm_combo.currentText()
        fast = self._fast_mode()

        fresh, stale = [], []
        for i, row in enumerate(self.model.rows):
            if row.status in ("pending", "error"):
                fresh.append(i)
            elif row.status == "done" and (row.rhythm_override != rhythm
                                           or row.fast_mode != fast):
                # Changing Rhythm or Fast invalidates finished rows, so they
                # get re-run — which on a large library is a long job the user
                # did not obviously ask for.
                stale.append(i)
        if stale and not self._confirm_reanalysis(len(stale), len(fresh)):
            return

        self._queue_rows(fresh + stale, rhythm)

    def _confirm_reanalysis(self, n_stale: int, n_fresh: int) -> bool:
        if n_stale < 25:
            return True
        new_part = (f" {n_fresh} track(s) have not been analyzed yet."
                    if n_fresh else " No tracks are new.")
        reply = QMessageBox.question(
            self, "Re-analyze",
            f"The Rhythm or Fast setting changed since those tracks were "
            f"analyzed, so {n_stale} finished track(s) will be analyzed "
            f"again.{new_part}\n\nRe-analyze them?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Yes)
        return reply == QMessageBox.Yes

    def _queue_rows(self, rows, rhythm: str | None = None) -> None:
        """Mark rows queued and hand them to the pool."""
        if rhythm is None:
            rhythm = self.rhythm_combo.currentText()
        fast = self._fast_mode()
        if not self._pending:
            # A fresh run: restart the throughput clock so the ETA is not
            # averaged against an earlier batch that may have used Fast mode.
            self._run_timer.restart()
            self._completions.clear()
        started = 0
        for i in rows:
            row = self.model.rows[i]
            row.rhythm_override = rhythm
            row.fast_mode = fast
            row.status = "queued"
            row.error = ""
            self.model.refresh_row(i)
            self.pool.start(AnalyzeTask(
                self.generation, i, row.path, rhythm, self.signals, fast))
            started += 1
        if started:
            self._pending += started
        self._update_progress()

    def _reanalyze_rows(self, rows: list[int], rhythm: str) -> None:
        self._queue_rows(rows, rhythm)

    def _on_started(self, gen: int, i: int) -> None:
        if gen != self.generation:
            return
        self.model.rows[i].status = "analyzing"
        self.model.refresh_row(i)

    def _on_done(self, gen: int, i: int, analysis) -> None:
        if gen != self.generation:
            return
        row = self.model.rows[i]
        row.analysis = analysis
        row.status = "done"
        self.model.refresh_row(i)
        self._pending -= 1
        self._note_completion()
        self._update_progress()
        self._save_soon()

    def _on_failed(self, gen: int, i: int, message: str) -> None:
        if gen != self.generation:
            return
        row = self.model.rows[i]
        row.status = "error"
        row.error = message
        self.model.refresh_row(i)
        self._pending -= 1
        self._note_completion()
        self._update_progress()
        self._save_soon()

    def _sync_actions(self) -> None:
        """Make every control's enabled state match what it can actually do.

        Previously only btn_analyze and btn_stop tracked the run, so the
        toolbar button greyed out mid-run while Ctrl+Return still fired, and
        Write tags / Export / Clear were always live — answering with a
        message box where a disabled item would have said it for free.
        """
        running = self._pending > 0
        analyzed = any(r.analysis is not None for r in self.model.rows)
        has_rows = bool(self.model.rows)
        has_selection = bool(self.table.selectionModel().selectedRows())

        self.btn_stop.setEnabled(running)
        self.act_stop.setEnabled(running)
        self.btn_analyze.setEnabled(not running and has_rows)
        self.act_analyze.setEnabled(not running and has_rows)
        # Not during a run: mutagen writing to a file a pool thread has open
        # for decoding is a sharing violation on Windows, and it surfaces as
        # a baffling PermissionError in the failure list.
        self.act_tags.setEnabled(analyzed and not running)
        self.act_csv.setEnabled(analyzed)
        self.act_json.setEnabled(analyzed)
        self.act_clear.setEnabled(has_rows)
        self.act_remove.setEnabled(has_selection)

    @staticmethod
    def _format_eta(seconds: float) -> str:
        if seconds < 45:
            return f"≈{max(5, int(round(seconds / 5) * 5))} s left"
        minutes = seconds / 60
        if minutes < 60:
            return f"≈{int(round(minutes))} min left"
        hours, mins = divmod(int(round(minutes)), 60)
        return f"≈{hours} h {mins:02d} min left"

    def _note_completion(self) -> None:
        if self._run_timer.isValid():
            self._completions.append(self._run_timer.elapsed())

    # A rate needs both enough completions and enough wall clock behind it.
    # The workers finish their first tracks almost together, so four
    # completions can span a fraction of a second and imply a rate an order of
    # magnitude too high — that burst alone predicted "5 s left" with 21 s to
    # go. Waiting for a real span costs a few seconds of silence and buys an
    # estimate that is right from the first time it appears.
    _ETA_MIN_COMPLETIONS = 4
    _ETA_MIN_SPAN_MS = 2500

    def _eta_text(self) -> str:
        """Time remaining, from the rate over the last few completions."""
        if len(self._completions) < self._ETA_MIN_COMPLETIONS:
            return ""
        span_ms = self._completions[-1] - self._completions[0]
        if span_ms < self._ETA_MIN_SPAN_MS:
            return ""
        rate = (len(self._completions) - 1) / (span_ms / 1000.0)
        if rate <= 0:
            return ""
        return " · " + self._format_eta(self._pending / rate)

    def _update_progress(self) -> None:
        done = sum(1 for r in self.model.rows if r.status == "done")
        errors = sum(1 for r in self.model.rows if r.status == "error")
        total = len(self.model.rows)
        running = self._pending > 0
        scanning = self._scans_running > 0
        self._sync_actions()

        self.progress_bar.setVisible(running or scanning)
        if scanning and not running:
            # Range 0,0 is Qt's busy indicator: a scan has no known length.
            self.progress_bar.setRange(0, 0)
        elif running:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done + errors)

        # The title carries the percentage so a minimised window still says
        # how far along it is from the taskbar.
        if running and total:
            percent = int(100 * (done + errors) / total)
            self.setWindowTitle(f"{percent}% — COMPAS")
        else:
            self.setWindowTitle("COMPAS — Tango Music Analyzer")

        if self.proxy.is_filtered() and not running and not scanning:
            # _report_filter owns the message while a filter is active.
            return

        suffix = f", {errors} failed" if errors else ""
        if running:
            self.statusBar().showMessage(
                f"Analyzing… {done}/{total} done "
                f"({self._pending} in flight{suffix}){self._eta_text()}")
        elif scanning:
            self.statusBar().showMessage("Scanning for audio files…")
        elif not total:
            self.statusBar().showMessage("No tracks loaded.")
        elif done + errors < total:
            # Reached by Stop, and by removing rows or clearing mid-run, which
            # both abandon the batch. Saying "Done" here was a plain lie: the
            # remaining rows are back to pending and nothing is running.
            self.statusBar().showMessage(
                f"Stopped — {done}/{total} analyzed{suffix}. "
                "Press Analyze to carry on with the rest.")
        else:
            hint = ("  Ctrl+Shift+F shows just the failures."
                    if errors else "")
            self.statusBar().showMessage(
                f"Done — {done}/{total} analyzed{suffix}.{hint}")

    def _abandon_in_flight(self) -> None:
        """Drop queued work and put unfinished rows back to 'pending'.

        Bumping the generation makes every in-flight result get discarded on
        arrival, including results for rows the user kept. Without resetting
        those rows they stay 'queued' forever and `_analyze_pending` will
        not pick them up again, so the only way to analyze them was
        right-click → Re-analyze. Clearing the pool matters too: otherwise a
        cancelled 500-track batch keeps four threads decoding audio while
        the status bar claims it stopped.
        """
        self.generation += 1
        self.pool.clear()
        self._pending = 0
        for i, row in enumerate(self.model.rows):
            if row.status in ("queued", "analyzing"):
                row.status = "pending"
                self.model.refresh_row(i)

    def _stop(self) -> None:
        if not self._pending:
            return
        self._abandon_in_flight()
        # _update_progress now reports the stopped state itself, so the run
        # can only be described one way however it was interrupted.
        self._update_progress()

    def closeEvent(self, event) -> None:
        # Otherwise closing during a run blocks on the global QThreadPool
        # draining every queued track, with no window left on screen.
        self.generation += 1
        self.scan_generation += 1
        self.pool.clear()
        self.scan_pool.clear()
        self._save_layout()
        # Synchronous, not debounced: the timer will never fire after this.
        self._save_session()
        super().closeEvent(event)

    # --- context menu ------------------------------------------------------
    def _selected_source_rows(self) -> list[int]:
        return sorted({
            self.proxy.mapToSource(ix).row()
            for ix in self.table.selectionModel().selectedRows()})

    def _context_menu(self, pos) -> None:
        rows = self._selected_source_rows()
        if not rows:
            return
        menu = QMenu(self)
        menu.addSection(f"{len(rows)} track(s) selected")
        for rhythm in RHYTHM_CHOICES:
            act = menu.addAction(f"Re-analyze as {rhythm}")
            act.triggered.connect(
                lambda checked=False, r=rhythm: self._reanalyze_rows(rows, r))
        menu.addSeparator()
        act_rm = menu.addAction("Remove from list")
        act_rm.triggered.connect(lambda: self._remove_rows(rows))
        # Windows passes a default-constructed point for the keyboard trigger
        # (Menu key / Shift+F10), which put the menu at the viewport's
        # top-left — next to a completely different track in a long list.
        if pos.isNull():
            pos = self.table.visualRect(self.table.currentIndex()).center()
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _remove_rows(self, rows: list[int]) -> None:
        if not rows:
            return
        # In-flight results are invalidated because the row indices shift,
        # so anything unfinished has to go back to pending or it is stranded.
        was_running = self._pending > 0
        self._abandon_in_flight()
        keep = [r for i, r in enumerate(self.model.rows) if i not in set(rows)]
        self.model.beginResetModel()
        self.model.rows = keep
        self.model.endResetModel()
        # A model reset drops the current index, so a second Del did nothing
        # until the user clicked a row again.
        if keep:
            self.table.setCurrentIndex(
                self.proxy.index(min(rows[0], len(keep) - 1), 0))
        if was_running:
            # Removing one bad file used to stop a 500-track batch dead, with
            # nothing but a status line to say so.
            self._analyze_pending()
            self.statusBar().showMessage(
                f"Removed {len(rows)} — resuming the run.")
        else:
            self._update_progress()
        self._save_soon()

    def _clear(self) -> None:
        analyzed = sum(1 for r in self.model.rows if r.analysis is not None)
        if analyzed:
            # There is no undo and no session persistence, so this is where
            # half an hour of analysis goes on a misclick.
            reply = QMessageBox.question(
                self, "Clear all",
                f"Discard {len(self.model.rows)} track(s), including "
                f"{analyzed} analyzed result(s)?\n\n"
                "Results that have not been exported or written to tags "
                "cannot be recovered.",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if reply != QMessageBox.Yes:
                return
        self._abandon_in_flight()
        # Any scan still walking a tree would otherwise repopulate the list
        # the user just emptied.
        self.scan_generation += 1
        self._scans_running = 0
        self.model.clear()
        self._clear_filters()
        self._save_session()          # at once: this is the destructive one
        self._update_progress()
        self.statusBar().showMessage("Cleared.")

    # --- help ---------------------------------------------------------------
    def _show_column_reference(self) -> None:
        """The per-column help, all in one place.

        It was only ever reachable by hovering a column header, which a new
        user has no reason to try — and half the columns start off-screen.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("What the columns mean")
        dlg.resize(660, 620)
        lay = QVBoxLayout(dlg)
        body = QTextBrowser()
        blocks = []
        for column in self.model.columns:
            help_ = column.tooltip or COLUMN_TOOLTIPS.get(column.header, "")
            if not help_:
                continue
            blocks.append(
                f"<p><b style='color:{theme.ACCENT_BRIGHT}'>"
                f"{html.escape(column.header)}</b><br>"
                f"{html.escape(help_).replace(chr(10), '<br>')}</p>")
        body.setHtml(
            f"<div style='color:{theme.TEXT_NORMAL}; font-size:10pt'>"
            + "".join(blocks) + "</div>")
        lay.addWidget(body)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        dlg.exec()

    def _show_about(self) -> None:
        QMessageBox.about(
            self, "About COMPAS",
            "<h3>COMPAS — Tango Music Analyzer</h3>"
            "<p>Measures tempo, key, energy and rhythmic character for tango, "
            "vals and milonga, and can write the results back into your "
            "files' tags for VirtualDJ.</p>"
            "<p><b>Getting started:</b> drop files or folders into the "
            "window, press <b>▶ Analyze</b>, then use "
            "<b>Output ▸ Write tags…</b>.</p>"
            "<p><b>Facets</b> turn the numbers into words — pick the axes and "
            "the vocabulary in the Facets menu. Hover any column header, or "
            "see <b>Help ▸ What the columns mean</b>, for what each number "
            "measures and how much to trust it.</p>")

    # --- outputs ----------------------------------------------------------
    def _analyzed_rows(self, prefer_selection: bool = True) -> list[TrackRow]:
        if prefer_selection:
            sel = [self.model.rows[i] for i in self._selected_source_rows()]
            done = [r for r in sel if r.analysis is not None]
            if done:
                return done
        return [r for r in self.model.rows if r.analysis is not None]

    def _write_tags(self) -> None:
        selected = [self.model.rows[i] for i in self._selected_source_rows()]
        in_selection = [r for r in selected if r.analysis is not None]
        all_analyzed = [r for r in self.model.rows if r.analysis is not None]
        if not all_analyzed:
            QMessageBox.information(
                self, "Write tags", "No analyzed tracks to write.")
            return
        if selected and not in_selection:
            # The old fallback silently widened the scope: select three
            # pending rows, press Ctrl+T, and one Enter wrote tags into every
            # analyzed file in the list.
            QMessageBox.information(
                self, "Write tags",
                f"None of the {len(selected)} selected track(s) have been "
                "analyzed yet.\n\nClear the selection to write tags for all "
                f"{len(all_analyzed)} analyzed track(s).")
            return

        rows = in_selection or all_analyzed
        dlg = WriteTagsDialog(self, rows, self.settings,
                              scoped_to_selection=bool(in_selection),
                              axis_keys=self.model.axis_keys,
                              vocabulary=self.model.vocabulary)
        if dlg.exec() != QDialog.Accepted:
            return
        opts = dlg.options()
        for k in ("bpm", "key", "compas", "facets", "comment"):
            self.settings.setValue(f"tags/{k}", opts[k])
        self.settings.setValue(
            "tags/key_format", "camelot" if opts["camelot"] else "standard")
        vocabulary = self.model.vocabulary if opts["facets"] else None

        from compas_core.tags import append_energy_comment, write_tags

        progress = QProgressDialog(
            "Writing tags…", "Cancel", 0, len(rows), self)
        progress.setWindowTitle("Write tags")
        progress.setWindowModality(Qt.WindowModal)
        # minimumDuration defaults to 4000 ms with the timer running from
        # construction, so any write shorter than four seconds — i.e. most of
        # them — showed no dialog at all while the UI blocked in the loop
        # below.
        progress.setMinimumDuration(0)
        progress.setValue(0)
        errors = []
        written = 0
        cancelled = False
        for n, row in enumerate(rows):
            progress.setValue(n)
            progress.setLabelText(f"Writing tags…\n{row.path.name}")
            QApplication.processEvents()
            if progress.wasCanceled():
                cancelled = True
                break
            try:
                write_tags(
                    row.path,
                    row.analysis.tag_fields(
                        key_as_camelot=opts["camelot"],
                        facet_vocabulary=vocabulary,
                        facet_axes=self.model.axis_keys),
                    write_bpm=opts["bpm"],
                    write_key=opts["key"],
                    write_compas=opts["compas"],
                )
                if opts["comment"]:
                    append_energy_comment(row.path, row.analysis.energy)
                written += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{row.path.name}: {exc}")
        progress.setValue(len(rows))
        progress.deleteLater()

        # Count as we go: QProgressDialog.setValue(maximum) triggers reset(),
        # after which value() is minimum - 1, so reading it back reported
        # "Tags written for -1 file(s)" on every successful run.
        summary = f"Tags written for {written} file(s)"
        if cancelled:
            summary += f" — cancelled, {len(rows) - written - len(errors)} skipped"
        if errors:
            QMessageBox.warning(
                self, "Write tags",
                f"{written} file(s) written, {len(errors)} failed:\n\n"
                + "\n".join(errors[:15])
                + (f"\n… and {len(errors) - 15} more" if len(errors) > 15 else ""))
            summary += f", {len(errors)} failed"
        self.statusBar().showMessage(summary + ".")

    def _export(self, kind: str) -> None:
        rows = self._analyzed_rows(prefer_selection=False)
        if not rows:
            QMessageBox.information(self, "Export", "Nothing analyzed yet.")
            return
        filt = "CSV (*.csv)" if kind == "csv" else "JSON (*.json)"
        name, _ = QFileDialog.getSaveFileName(
            self, f"Export {kind.upper()}", f"compas_results.{kind}", filt)
        if not name:
            return
        # to_dict() is the raw dataclass, so the facet columns the table shows
        # and Write tags can store were the one thing missing from an export.
        axis_keys = self.model.axis_keys
        vocabulary = self.model.vocabulary
        axes = facets.resolve_axes(axis_keys)
        dicts = []
        for r in rows:
            d = r.analysis.to_dict()
            for axis in axes:
                d[f"facet_{axis.key}"] = facets.axis_label(
                    axis, r.analysis, vocabulary)
            if axes:
                d["facets"] = facets.label(r.analysis, vocabulary, axis_keys)
            dicts.append(d)
        if kind == "csv":
            with open(name, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(dicts[0].keys()))
                w.writeheader()
                w.writerows(dicts)
        else:
            Path(name).write_text(
                json.dumps(dicts, indent=2), encoding="utf-8")
        self.statusBar().showMessage(f"Exported {len(dicts)} rows to {name}")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("COMPAS")
    app.setOrganizationName("compas")
    theme.apply_theme(app)
    win = MainWindow()
    win.show()
    theme.apply_dark_title_bar(win)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
