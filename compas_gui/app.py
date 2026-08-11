"""COMPAS GUI — main window.

Run with:  python -m compas_gui
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QSortFilterProxyModel, Qt, QThreadPool
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableView,
    QToolBar,
    QToolButton,
    QVBoxLayout,
)

from compas_core import facets
from compas_gui import theme
from compas_gui.model import (
    COLUMN_TOOLTIPS,
    METRIC_COLUMNS,
    TrackRow,
    TrackTableModel,
)
from compas_gui.workers import (
    AnalyzeTask,
    LibrosaWarmup,
    WorkerSignals,
    suggested_thread_count,
)

AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".aiff", ".wma"}
RHYTHM_CHOICES = ["auto", "tango", "vals", "milonga"]

# Columns that can never be hidden via the Columns menu.
ALWAYS_VISIBLE_COLUMNS = {"File", "Status"}

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


def collect_audio_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(
                f for f in p.rglob("*") if f.suffix.lower() in AUDIO_EXTS))
        elif p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            files.append(p)
    return files


class WriteTagsDialog(QDialog):
    """Options for writing analysis results into file tags."""

    def __init__(self, parent, n_tracks: int, settings: QSettings) -> None:
        super().__init__(parent)
        self.setWindowTitle("Write tags")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            f"Write analysis results into the tags of {n_tracks} file(s).\n"
            "Existing tag fields not listed below are left untouched."))

        self.cb_bpm = QCheckBox("BPM (standard tag — VirtualDJ reads this)")
        self.cb_key = QCheckBox("Initial key (standard tag)")
        self.cb_compas = QCheckBox(
            "COMPAS_* fields (energy, drive, articulation, texture, "
            "harmony, voice, stability, timing, BPM range…)")
        self.cb_facets = QCheckBox(
            "COMPAS_FACETS — the composed phrase, in the vocabulary and "
            "axes currently selected")
        self.cb_comment = QCheckBox(
            "Append \"COMPAS Energy N\" to the comment "
            "(keeps existing comment text)")
        self.cb_bpm.setChecked(settings.value("tags/bpm", True, bool))
        self.cb_key.setChecked(settings.value("tags/key", True, bool))
        self.cb_compas.setChecked(settings.value("tags/compas", True, bool))
        self.cb_facets.setChecked(settings.value("tags/facets", True, bool))
        self.cb_comment.setChecked(settings.value("tags/comment", False, bool))
        self.cb_facets.setEnabled(self.cb_compas.isChecked())
        self.cb_compas.toggled.connect(self.cb_facets.setEnabled)

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
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def options(self) -> dict:
        return {
            "bpm": self.cb_bpm.isChecked(),
            "key": self.cb_key.isChecked(),
            "compas": self.cb_compas.isChecked(),
            "facets": self.cb_facets.isChecked(),
            "comment": self.cb_comment.isChecked(),
            "camelot": self.key_format.currentIndex() == 1,
        }


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("COMPAS — Tango Music Analyzer")
        self.resize(1240, 640)
        self.setAcceptDrops(True)
        self.settings = QSettings("compas", "compas")

        self.model = TrackTableModel(self._facet_axes(), self._vocabulary())
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.UserRole)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 340)
        self.setCentralWidget(self.table)

        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(suggested_thread_count())
        self.pool.start(LibrosaWarmup())

        self.signals = WorkerSignals()
        self.signals.started.connect(self._on_started)
        self.signals.done.connect(self._on_done)
        self.signals.failed.connect(self._on_failed)
        self.generation = 0
        self._pending = 0

        self._build_toolbar()
        self._apply_column_visibility()
        self.statusBar().showMessage(
            "Add files or drop them anywhere in the window, then press Analyze.")

    # --- UI scaffolding -------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        act_files = QAction("Add files…", self)
        act_files.triggered.connect(self._add_files)
        tb.addAction(act_files)

        act_folder = QAction("Add folder…", self)
        act_folder.triggered.connect(self._add_folder)
        tb.addAction(act_folder)

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
            "Analyze all pending files (Ctrl+Return)")
        self.btn_analyze.setShortcut(QKeySequence("Ctrl+Return"))
        self.btn_analyze.clicked.connect(self._analyze_pending)
        tb.addWidget(self.btn_analyze)

        tb.addSeparator()
        act_tags = QAction("Write tags…", self)
        act_tags.triggered.connect(self._write_tags)
        tb.addAction(act_tags)

        act_csv = QAction("Export CSV…", self)
        act_csv.triggered.connect(lambda: self._export("csv"))
        tb.addAction(act_csv)

        act_json = QAction("Export JSON…", self)
        act_json.triggered.connect(lambda: self._export("json"))
        tb.addAction(act_json)

        tb.addSeparator()
        btn_columns = QToolButton()
        btn_columns.setText("Columns ▾")
        btn_columns.setToolTip("Choose which metrics are shown in the table.")
        btn_columns.setPopupMode(QToolButton.InstantPopup)
        btn_columns.setMenu(self._build_columns_menu())
        tb.addWidget(btn_columns)

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

        tb.addSeparator()
        act_clear = QAction("Clear", self)
        act_clear.triggered.connect(self._clear)
        tb.addAction(act_clear)

    # --- column visibility ------------------------------------------------
    def _hidden_columns(self) -> set[str]:
        try:
            hidden = set(json.loads(
                self.settings.value("columns/hidden", "[]", str)))
        except (TypeError, ValueError):
            hidden = set()
        return hidden - ALWAYS_VISIBLE_COLUMNS

    def _build_columns_menu(self) -> QMenu:
        menu = StayOpenMenu(self)
        menu.setToolTipsVisible(True)
        hidden = self._hidden_columns()
        # Metric columns come first and keep their indices when facet
        # columns are added or removed, so this menu never needs rebuilding.
        for col, column in enumerate(METRIC_COLUMNS):
            if column.header in ALWAYS_VISIBLE_COLUMNS:
                continue
            act = QAction(column.header, menu)
            act.setToolTip(COLUMN_TOOLTIPS.get(column.header, ""))
            act.setCheckable(True)
            act.setChecked(column.header not in hidden)
            act.toggled.connect(
                lambda shown, c=col, h=column.header: self._set_column_shown(
                    c, h, shown))
            menu.addAction(act)
        return menu

    def _set_column_shown(self, col: int, header: str, shown: bool) -> None:
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
        raw = self.settings.value("facets/axes", None, str)
        if raw is None:
            return facets.DEFAULT_AXIS_KEYS
        try:
            keys = json.loads(raw)
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
        header = menu.addAction("Vocabulary")
        header.setEnabled(False)
        self._vocab_actions: dict[str, QAction] = {}
        for name in facets.VOCABULARIES:
            act = QAction(f"   {VOCABULARY_LABELS[name]}", menu)
            act.setCheckable(True)
            act.setChecked(name == vocabulary)
            act.setToolTip(
                "Words for the same thresholds: "
                + ", ".join(a.labels[name][-1] for a in facets.AXES[:4]) + "…")
            act.toggled.connect(
                lambda on, v=name: on and self._set_vocabulary(v))
            menu.addAction(act)
            self._vocab_actions = getattr(self, "_vocab_actions", {})
            self._vocab_actions[name] = act

        menu.addSeparator()
        axes_header = menu.addAction("Axes to compare over")
        axes_header.setEnabled(False)
        selected = set(self._facet_axes())
        for axis in facets.AXES:
            act = QAction(f"   {axis.name}", menu)
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
        for name, act in getattr(self, "_vocab_actions", {}).items():
            act.blockSignals(True)
            act.setChecked(name == vocabulary)
            act.blockSignals(False)
        self._rebuild_facet_columns(self.model.axis_keys, vocabulary)

    def _set_axis_selected(self, key: str, selected: bool) -> None:
        keys = [a.key for a in facets.AXES
                if (a.key in self.model.axis_keys or a.key == key)
                and (a.key != key or selected)]
        self.settings.setValue("facets/axes", json.dumps(keys))
        self._rebuild_facet_columns(keys, self.model.vocabulary)

    def _rebuild_facet_columns(self, axis_keys, vocabulary: str) -> None:
        # A model reset drops per-column state, so re-apply what the view
        # owns: hidden metric columns and the File column's width.
        self.model.set_facets(axis_keys, vocabulary)
        self._apply_column_visibility()
        self.table.setColumnWidth(0, 340)

    # --- adding files ----------------------------------------------------
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
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
        files = collect_audio_files(paths)
        if files:
            self.model.add_paths(files)
            self.statusBar().showMessage(
                f"{len(self.model.rows)} file(s) loaded — press Analyze.")

    # --- analysis --------------------------------------------------------
    def _fast_mode(self) -> bool:
        return self.fast_check.isChecked()

    def _analyze_pending(self) -> None:
        rhythm = self.rhythm_combo.currentText()
        fast = self._fast_mode()
        started = 0
        for i, row in enumerate(self.model.rows):
            if row.status in ("pending", "error") or (
                    row.status == "done"
                    and (row.rhythm_override != rhythm
                         or row.fast_mode != fast)):
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
        fast = self._fast_mode()
        for i in rows:
            row = self.model.rows[i]
            row.rhythm_override = rhythm
            row.fast_mode = fast
            row.status = "queued"
            row.error = ""
            self.model.refresh_row(i)
            self.pool.start(AnalyzeTask(
                self.generation, i, row.path, rhythm, self.signals, fast))
        self._pending += len(rows)
        self._update_progress()

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
        self._update_progress()

    def _on_failed(self, gen: int, i: int, message: str) -> None:
        if gen != self.generation:
            return
        row = self.model.rows[i]
        row.status = "error"
        row.error = message
        self.model.refresh_row(i)
        self._pending -= 1
        self._update_progress()

    def _update_progress(self) -> None:
        done = sum(1 for r in self.model.rows if r.status == "done")
        total = len(self.model.rows)
        if self._pending > 0:
            self.statusBar().showMessage(
                f"Analyzing… {done}/{total} done ({self._pending} in flight)")
        else:
            self.statusBar().showMessage(f"Done — {done}/{total} analyzed.")

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
        for rhythm in RHYTHM_CHOICES:
            act = menu.addAction(f"Re-analyze as {rhythm}")
            act.triggered.connect(
                lambda checked=False, r=rhythm: self._reanalyze_rows(rows, r))
        menu.addSeparator()
        act_rm = menu.addAction("Remove from list")
        act_rm.triggered.connect(lambda: self._remove_rows(rows))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _remove_rows(self, rows: list[int]) -> None:
        # Invalidate in-flight results (row indices shift), then rebuild.
        self.generation += 1
        self._pending = 0
        keep = [r for i, r in enumerate(self.model.rows) if i not in set(rows)]
        self.model.beginResetModel()
        self.model.rows = keep
        self.model.endResetModel()

    def _clear(self) -> None:
        self.generation += 1
        self._pending = 0
        self.model.clear()
        self.statusBar().showMessage("Cleared.")

    # --- outputs ----------------------------------------------------------
    def _analyzed_rows(self, prefer_selection: bool = True) -> list[TrackRow]:
        if prefer_selection:
            sel = [self.model.rows[i] for i in self._selected_source_rows()]
            done = [r for r in sel if r.analysis is not None]
            if done:
                return done
        return [r for r in self.model.rows if r.analysis is not None]

    def _write_tags(self) -> None:
        rows = self._analyzed_rows()
        if not rows:
            QMessageBox.information(
                self, "Write tags", "No analyzed tracks to write.")
            return
        dlg = WriteTagsDialog(self, len(rows), self.settings)
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
        progress.setWindowModality(Qt.WindowModal)
        errors = []
        for n, row in enumerate(rows):
            progress.setValue(n)
            QApplication.processEvents()
            if progress.wasCanceled():
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
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{row.path.name}: {exc}")
        progress.setValue(len(rows))

        if errors:
            QMessageBox.warning(
                self, "Write tags",
                "Some files failed:\n" + "\n".join(errors[:15]))
        else:
            self.statusBar().showMessage(
                f"Tags written for {min(len(rows), progress.value())} file(s).")

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
        dicts = [r.analysis.to_dict() for r in rows]
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
