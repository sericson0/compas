"""Table model for the results view."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from compas_core.analyze import TrackAnalysis

_SRC_ABBR = {"override": "set", "genre-tag": "tag", "audio": "audio", "default": "dflt"}

_RHYTHM_COLORS = {
    "tango": QColor(66, 133, 244, 28),
    "vals": QColor(52, 168, 83, 28),
    "milonga": QColor(244, 180, 0, 32),
}


@dataclass
class TrackRow:
    path: Path
    status: str = "pending"      # pending / analyzing / done / error
    error: str = ""
    rhythm_override: str = "auto"
    analysis: TrackAnalysis | None = None


def _a(row: TrackRow, attr: str, fmt: str = "{}"):
    if row.analysis is None:
        return ""
    return fmt.format(getattr(row.analysis, attr))


# (header, display_fn, sort_fn)
COLUMNS = [
    ("File", lambda r: r.path.name, lambda r: r.path.name.lower()),
    ("Rhythm",
     lambda r: (f"{r.analysis.rhythm} ({_SRC_ABBR.get(r.analysis.rhythm_source, '?')})"
                if r.analysis else
                ("" if r.rhythm_override == "auto" else r.rhythm_override)),
     lambda r: r.analysis.rhythm if r.analysis else ""),
    ("BPM", lambda r: _a(r, "bpm", "{:.1f}"),
     lambda r: r.analysis.bpm if r.analysis else -1),
    ("BPM range",
     lambda r: (f"{r.analysis.bpm_low:.0f}–{r.analysis.bpm_high:.0f}"
                if r.analysis else ""),
     lambda r: (r.analysis.bpm_high - r.analysis.bpm_low) if r.analysis else -1),
    ("Bars/min", lambda r: _a(r, "bars_per_min", "{:.1f}"),
     lambda r: r.analysis.bars_per_min if r.analysis else -1),
    ("Stability", lambda r: _a(r, "stability", "{:.0f}"),
     lambda r: r.analysis.stability if r.analysis else -1),
    ("Timing", lambda r: _a(r, "timing"),
     lambda r: r.analysis.timing if r.analysis else ""),
    ("Key", lambda r: _a(r, "key"), lambda r: r.analysis.key if r.analysis else ""),
    ("Camelot", lambda r: _a(r, "camelot"),
     lambda r: r.analysis.camelot if r.analysis else ""),
    ("Tag BPM/key",
     lambda r: (" · ".join(x for x in (r.analysis.tag_bpm, r.analysis.tag_key) if x)
                if r.analysis else ""),
     lambda r: (r.analysis.tag_key or "") if r.analysis else ""),
    ("Energy", lambda r: _a(r, "energy", "{:.1f}"),
     lambda r: r.analysis.energy if r.analysis else -1),
    ("Drive", lambda r: _a(r, "drive", "{:.0f}"),
     lambda r: r.analysis.drive if r.analysis else -1),
    ("Dyn (dB)", lambda r: _a(r, "dynamic_range_db", "{:.1f}"),
     lambda r: r.analysis.dynamic_range_db if r.analysis else -1),
    ("Status", lambda r: r.error if r.status == "error" else r.status,
     lambda r: r.status),
]

_NUMERIC_COLS = {2, 3, 4, 5, 10, 11, 12}


class TrackTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[TrackRow] = []

    # --- Qt plumbing -----------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section][0]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return COLUMNS[col][1](row)
        if role == Qt.UserRole:
            return COLUMNS[col][2](row)
        if role == Qt.TextAlignmentRole and col in _NUMERIC_COLS:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.BackgroundRole and row.analysis is not None:
            return _RHYTHM_COLORS.get(row.analysis.rhythm)
        if role == Qt.ToolTipRole and row.status == "error":
            return row.error
        return None

    # --- mutation helpers ---------------------------------------------------
    def add_paths(self, paths: list[Path]) -> None:
        existing = {r.path for r in self.rows}
        fresh = [TrackRow(path=p) for p in paths if p not in existing]
        if not fresh:
            return
        first = len(self.rows)
        self.beginInsertRows(QModelIndex(), first, first + len(fresh) - 1)
        self.rows.extend(fresh)
        self.endInsertRows()

    def clear(self) -> None:
        self.beginResetModel()
        self.rows.clear()
        self.endResetModel()

    def refresh_row(self, i: int) -> None:
        if 0 <= i < len(self.rows):
            self.dataChanged.emit(
                self.index(i, 0), self.index(i, len(COLUMNS) - 1))
