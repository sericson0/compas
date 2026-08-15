"""Table model for the results view.

Columns come in two kinds. The **metric** columns are fixed and show the
numbers COMPAS measured. The **facet** columns are built on the fly from
whichever axes are ticked in the Facets menu: each one renders a metric as
a word, in either vocabulary, and a "Facets" column composes them into a
phrase. They carry a ≡ prefix so it stays obvious which columns are
measurements and which are readings of a measurement.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QColor

from compas_core import facets
from compas_core.analyze import RHYTHM_CONFIDENCE_FLOOR, TrackAnalysis

_SRC_ABBR = {"override": "set", "genre-tag": "tag", "audio": "audio", "default": "dflt"}

FACET_PREFIX = "≡ "     # ≡ — marks a column as a reading, not a number

# Translucent tints over the dark table background. Alphas are not equal
# because the hues are not: amber carries far more luminance than blue at the
# same opacity, so the old flat 40/40/36 made milonga the loudest of the three
# (1.27 lift against tango's 1.20). These are solved per hue for an equal
# ~1.28 lift, which keeps the zebra visible inside a tint (1.16:1) and text
# above 6:1 on all six composites.
_RHYTHM_COLORS = {
    "tango": QColor(66, 133, 244, 52),
    "vals": QColor(52, 168, 83, 48),
    "milonga": QColor(244, 180, 0, 37),
}

_STATUS_COLORS = {
    # #5a5e70 is the value theme.py flags as unreadable (3.0:1 on the panel,
    # 2.2:1 on a tinted alternating row) — and "queued" is the state every row
    # sits in for the first seconds of a large batch.
    "queued": QColor(0x9a, 0xa0, 0xb4),
    "analyzing": QColor(0xF3, 0xA1, 0x0F),
    "done": QColor(0x4C, 0xAF, 0x50),
    "error": QColor(0xF4, 0x43, 0x36),
}


@dataclass
class TrackRow:
    path: Path
    status: str = "pending"      # pending / analyzing / done / error
    error: str = ""
    rhythm_override: str = "auto"
    fast_mode: bool = False
    analysis: TrackAnalysis | None = None


@dataclass(frozen=True)
class Column:
    # `header` is the stable identity: the Columns menu label, the
    # COLUMN_TOOLTIPS key, and the key stored in the columns/hidden setting.
    # `short` is only what the table paints, so headers can be abbreviated
    # without invalidating anyone's saved column choices.
    header: str
    display: Callable[[TrackRow], str]
    sort: Callable[[TrackRow], Any]
    numeric: bool = False
    tooltip: str = ""            # full help — header and Columns menu
    summary: str = ""            # one-line form — cells
    facet: bool = False          # built from the Facets menu, not toggleable
    # True when an unanalyzed row has no real value in this column, so sorting
    # should park it at the end rather than sort it by a sentinel. False for
    # File and Status, which read fine before analysis.
    sinks_pending: bool = True
    short: str = ""              # painted header; falls back to `header`
    searchable: bool = False     # included in the filter box's haystack

    @property
    def label(self) -> str:
        return self.short or self.header


def _a(row: TrackRow, attr: str, fmt: str = "{}"):
    if row.analysis is None:
        return ""
    return fmt.format(getattr(row.analysis, attr))


def _opt(row: TrackRow, attr: str, fmt: str = "{}"):
    """Like _a, but renders None as an em dash rather than 'None'."""
    if row.analysis is None:
        return ""
    val = getattr(row.analysis, attr)
    return "—" if val is None else fmt.format(val)


def _num(row: TrackRow, attr: str, missing: float = -1.0):
    return getattr(row.analysis, attr) if row.analysis else missing


def _rhythm_label(row: TrackRow) -> str:
    """e.g. 'tango (tag)', or 'vals (audio?)' when the guess is shaky."""
    a = row.analysis
    if a is None:
        return "" if row.rhythm_override == "auto" else row.rhythm_override
    src = _SRC_ABBR.get(a.rhythm_source, "?")
    if a.rhythm_source == "audio" and a.rhythm_confidence < RHYTHM_CONFIDENCE_FLOOR:
        src += "?"
    return f"{a.rhythm} ({src})"


# Vocal presence is disabled — see compas_core/analyze.py for why.
# def _vocal_label(row: TrackRow) -> str:
#     """'instrumental (tag)', or 'vocal ?' when the audio call is close."""
#     a = row.analysis
#     if a is None:
#         return ""
#     if a.vocal_source == "title":
#         return f"{a.vocal} (tag)"
#     return a.vocal + (" ?" if a.vocal_confidence < 0.25 else "")


# Shown on the header, on every cell of the column, and in the Columns menu.
_COLUMN_HELP = {
    "File": "Filename on disk. Drop files or folders anywhere in the window "
            "to add more.",
    "Rhythm": "Song type, and where it came from:\n"
              "  set — you forced it (toolbar or right-click)\n"
              "  tag — read from the file's GENRE tag\n"
              "  audio — guessed from the audio; 'audio?' means the guess is "
              "shaky and worth checking\n"
              "Rows are tinted by rhythm: tango blue, vals green, milonga "
              "amber.",
    "BPM": "Beat-level tempo — the pulse a dancer steps to — as the median "
           "of the local tempo curve.\n"
           "Vals is counted at the quarter note (≈150–215), not the bar.",
    "BPM range": "10th–90th percentile of the local tempo curve: the honest "
                 "spread of the track.\n"
                 "A wide range means the orchestra drifts or pushes and "
                 "pulls; sorts by width.",
    "Bars/min": "Bars per minute (BPM ÷ beats per bar).\n"
                "The fair way to compare a vals against a tango — 200 BPM in "
                "3/4 is ~67 bars/min, slower than it sounds.",
    "Stability": "0–100, how steady the tempo is. Higher = metronomic.\n"
                 "Measured on the detrended tempo curve, so a gradual "
                 "accelerando does not count against it — only local rubato "
                 "does.",
    "Timing": "fixed = steady enough to dance without surprises; flexible = "
              "noticeable rubato.\n"
              "Derived from Stability, with a more lenient bar for vals.",
    "Key": "Estimated musical key (e.g. Dm), from chroma profile matching "
           "plus the final chord.\n"
           "78 rpm transfers were not always at exact speed, so treat this "
           "as approximate on golden-age material.",
    "Camelot": "The same key as a Camelot wheel code (e.g. 7A) for "
               "harmonic mixing.",
    "Tag BPM/key": "BPM and initial key already in the file's tags from "
                   "another tool (Mixed In Key, Serato…).\n"
                   "Shown for comparison only — COMPAS never overwrites them "
                   "unless you use Write tags.",
    "Energy": "1–10 overall lift: how much this track will move a floor.\n"
              "A blend of Drive and Sync (half the score), tempo relative to "
              "the genre's typical, onset density, and loudness variation.",
    "Drive": "0–100, how hard the compás is marked.\n"
             "On-beat versus off-beat attack in the bass and bandoneón bands "
             "— D'Arienzo's marcato scores high, a legato Di Sarli low, "
             "regardless of tempo or volume.",
    "Sync": "0–100, how much rhythmic weight falls between the beats.\n"
            "Milonga's habanera scores high; straight marking scores low. "
            "Largely independent of Drive.",
    "Artic": "0–100, how detached the playing is: attack sharpness plus how "
             "far each note falls away before the next one.\n"
             "Measured in fixed 50/140 ms windows, so it is not a restatement "
             "of tempo. Related to Drive (r≈0.73) but not the same — Victor's "
             "Temo marks hard with the softest attacks in the corpus.",
    "Texture": "0–100, percussive versus sustained.\n"
               "From the anisotropy of the spectrogram: percussive energy "
               "changes fast in time and slowly in frequency, harmonic energy "
               "the reverse. Effectively independent of Drive (r≈0.06), so it "
               "is a genuinely separate axis.",
    "Harmony": "0–100, how many distinct harmonies the piece uses.\n"
               "PROVISIONAL — the least validated number in COMPAS. Chroma is "
               "smeared on shellac, and this agrees with a hand-written "
               "expert ordering of 19 tracks at only Spearman 0.41. Calibrate "
               "it on your own library before trusting it.",
    # "Vocal" is disabled — see compas_core/analyze.py for why.
    "Status": "pending → queued → analyzing → done.\n"
              "A track that failed shows its error message here instead; "
              "hovering it gives the full text.",
}


def _wrap(text: str, width: int = 64) -> str:
    """Hard-wrap help text — Qt does not word-wrap plain-text tooltips, so a
    long line would render as one absurdly wide strip."""
    out = []
    for para in text.split("\n"):
        indent = para[: len(para) - len(para.lstrip())]
        # Continuation lines only hang under a line that was itself indented,
        # i.e. the bulleted lists — flowing prose stays flush left.
        out.append(textwrap.fill(
            para.strip(), width=width, initial_indent=indent,
            subsequent_indent=indent + "  " if indent else "",
            # These wrap Windows paths and exception text as often as prose,
            # and chopping "C:\Users\…\Di Sarli" mid-token to hit column 64
            # makes it unreadable. Better one over-long line than a broken
            # path.
            break_long_words=False, break_on_hyphens=False))
    return "\n".join(out)


COLUMN_TOOLTIPS = {header: _wrap(help_) for header, help_ in _COLUMN_HELP.items()}

# Every _COLUMN_HELP entry is written as "one-line definition\ndetail…", so the
# first line is a ready-made short form. Headers get the essay; cells — which
# the user sweeps across by the dozen while comparing tracks — get one line.
COLUMN_SUMMARIES = {header: _wrap(help_.split("\n")[0])
                    for header, help_ in _COLUMN_HELP.items()}


# Painted header for columns whose full name is too wide to spend on a
# two-to-five character number. The full name stays in the Columns menu, the
# tooltip and Help ▸ What the columns mean.
_SHORT_HEADERS = {
    "BPM range": "BPM ±",
    "Bars/min": "Bars",
    "Stability": "Stab",
    "Camelot": "Cam",
    "Tag BPM/key": "Tags",
    "Texture": "Tex",
    "Harmony": "Harm",
    "LRA (LU)": "LRA",
}

# Facet axis names are domain vocabulary and used by the CLI, so they are
# abbreviated only for painting, keyed on the axis name.
_SHORT_AXIS_NAMES = {
    "Character": "Char",
    "Articulation": "Artic",
    "Placement": "Place",
    "Phrasing": "Phras",
    "Dynamics": "Dyn",
    "Harmony": "Harm",
    "Texture": "Tex",
}


def _metric_columns() -> list[Column]:
    def col(header: str, display, sort, numeric: bool = False,
            sinks_pending: bool = True, searchable: bool = False) -> Column:
        return Column(header, display, sort, numeric,
                      COLUMN_TOOLTIPS.get(header, ""),
                      COLUMN_SUMMARIES.get(header, ""),
                      sinks_pending=sinks_pending,
                      short=_SHORT_HEADERS.get(header, ""),
                      searchable=searchable)

    return [
        col("File", lambda r: r.path.name, lambda r: r.path.name.lower(),
            sinks_pending=False, searchable=True),
        col("Rhythm", _rhythm_label,
            lambda r: r.analysis.rhythm if r.analysis else "",
            searchable=True),
        col("BPM", lambda r: _a(r, "bpm", "{:.1f}"),
            lambda r: _num(r, "bpm"), True),
        col("BPM range",
            lambda r: (f"{r.analysis.bpm_low:.0f}–{r.analysis.bpm_high:.0f}"
                       if r.analysis else ""),
            lambda r: ((r.analysis.bpm_high - r.analysis.bpm_low)
                       if r.analysis else -1), True),
        col("Bars/min", lambda r: _a(r, "bars_per_min", "{:.1f}"),
            lambda r: _num(r, "bars_per_min"), True),
        col("Stability", lambda r: _a(r, "stability", "{:.0f}"),
            lambda r: _num(r, "stability"), True),
        col("Timing", lambda r: _a(r, "timing"),
            lambda r: r.analysis.timing if r.analysis else "",
            searchable=True),
        col("Key", lambda r: _a(r, "key"),
            lambda r: r.analysis.key if r.analysis else "",
            searchable=True),
        col("Camelot", lambda r: _a(r, "camelot"),
            lambda r: r.analysis.camelot if r.analysis else "",
            searchable=True),
        col("Tag BPM/key",
            lambda r: (" · ".join(x for x in (r.analysis.tag_bpm,
                                              r.analysis.tag_key) if x)
                       if r.analysis else ""),
            lambda r: (r.analysis.tag_key or "") if r.analysis else ""),
        col("Energy", lambda r: _a(r, "energy", "{:.1f}"),
            lambda r: _num(r, "energy"), True),
        col("Drive", lambda r: _a(r, "drive", "{:.0f}"),
            lambda r: _num(r, "drive"), True),
        col("Sync", lambda r: _a(r, "syncopation", "{:.0f}"),
            lambda r: _num(r, "syncopation"), True),
        col("Artic", lambda r: _a(r, "articulation", "{:.0f}"),
            lambda r: _num(r, "articulation"), True),
        col("Texture", lambda r: _a(r, "percussiveness", "{:.0f}"),
            lambda r: _num(r, "percussiveness"), True),
        col("Harmony", lambda r: _a(r, "harmonic_variety", "{:.0f}"),
            lambda r: _num(r, "harmonic_variety"), True),
        # Vocal presence disabled — see compas_core/analyze.py for why.
        # col("Vocal", _vocal_label,
        #     lambda r: r.analysis.vocal if r.analysis else ""),
        col("LUFS", lambda r: _opt(r, "lufs", "{:.1f}"),
            lambda r: (r.analysis.lufs if r.analysis
                       and r.analysis.lufs is not None else -999), True),
        col("LRA (LU)", lambda r: _opt(r, "lra", "{:.1f}"),
            lambda r: (r.analysis.lra if r.analysis
                       and r.analysis.lra is not None else -1), True),
    ]


METRIC_COLUMNS = _metric_columns()
METRIC_HEADERS = [c.header for c in METRIC_COLUMNS]

_STATUS_COLUMN = Column(
    "Status",
    # Just the state word. It used to substitute the whole exception string,
    # which cannot survive in a column narrow enough to sit at the left edge
    # — the message is on the tooltip, and View ▸ Show only failed tracks
    # collects the rows it applies to.
    lambda r: r.status,
    lambda r: r.status,
    tooltip=COLUMN_TOOLTIPS["Status"],
    summary=COLUMN_SUMMARIES["Status"],
    sinks_pending=False,
    searchable=True,
)


def _facet_column(axis: facets.Axis, vocabulary: str) -> Column:
    levels = " / ".join(axis.labels.get(vocabulary, axis.labels[facets.ENGLISH]))
    tip = _wrap(f"{levels}\n\n{axis.help}\n\n"
                "A facet is a threshold over a column, not a new measurement "
                "— the number it came from is still in the table. Thresholds "
                "are provisional; see scripts/calibrate_facets.py.")
    return Column(
        header=FACET_PREFIX + axis.name,
        display=lambda r, ax=axis, v=vocabulary: (
            facets.axis_label(ax, r.analysis, v) if r.analysis else ""),
        sort=lambda r, ax=axis: (
            lvl if (lvl := facets.axis_level(ax, r.analysis)) is not None
            else -1),
        tooltip=tip,
        summary=_wrap(f"{levels} — {axis.help.split('.')[0]}."),
        facet=True,
        short=(FACET_PREFIX + _SHORT_AXIS_NAMES[axis.name]
               if axis.name in _SHORT_AXIS_NAMES else ""),
        searchable=True,
    )


def build_columns(axis_keys, vocabulary: str) -> list[Column]:
    """File, Status, the remaining metrics, then one column per selected axis.

    Status sits second rather than last because it is the run's only per-row
    feedback, and at the far right of a twenty-column table it spent the whole
    analysis off the edge of the viewport.
    """
    columns = [METRIC_COLUMNS[0], _STATUS_COLUMN, *METRIC_COLUMNS[1:]]
    axes = facets.resolve_axes(axis_keys)
    columns.extend(_facet_column(a, vocabulary) for a in axes)
    if axes:
        keys = tuple(a.key for a in axes)
        columns.append(Column(
            header="Facets",
            display=lambda r, k=keys, v=vocabulary: (
                facets.label(r.analysis, v, k) if r.analysis else ""),
            sort=lambda r, k=keys, v=vocabulary: (
                facets.label(r.analysis, v, k) if r.analysis else ""),
            tooltip=_wrap(
                "The selected facets composed into one phrase, skipping any "
                "axis on which the track is unremarkable — so 'fast driving "
                "instrumental' rather than 'fast driving mixed balanced "
                "steady instrumental'.\n\n"
                "Choose the axes and the vocabulary in the Facets menu. "
                "Write tags… can put this phrase in a COMPAS_FACETS tag."),
            summary=_wrap("The selected facets composed into one phrase, "
                          "skipping any axis on which the track is "
                          "unremarkable."),
            facet=True,
            searchable=True,
        ))
    return columns


def _cell_note(row: TrackRow, header: str) -> str | None:
    """Row-specific detail shown under the column's explanation."""
    if header == "File":
        return _wrap(str(row.path))
    a = row.analysis
    if a is None:
        return None
    if header == "Rhythm" and a.rhythm_source == "audio":
        note = ("Low confidence — no GENRE tag, so this was guessed from the "
                "audio. Worth setting by hand."
                if a.rhythm_confidence < RHYTHM_CONFIDENCE_FLOOR
                else "Guessed from audio (no GENRE tag).")
        return _wrap(f"This track: {note}\nConfidence {a.rhythm_confidence:.2f}")
    if header in ("Key", "Camelot"):
        return f"This track: confidence {a.key_confidence:.0f}/100"
    if header == "Timing":
        return (f"This track: stability {a.stability:.0f}, "
                f"tempo spread {a.bpm_low:.0f}–{a.bpm_high:.0f} BPM")
    if header == "Artic":
        return (f"This track: attack {a.raw_attack_db:.1f} dB, "
                f"release {a.raw_release_db:.1f} dB")
    if header == "Texture":
        return f"This track: anisotropy {a.raw_anisotropy:.4f}"
    if header == "Harmony":
        return (f"This track: effective rank {a.raw_eff_rank:.2f}, "
                f"chord change {a.raw_chord_change:.3f}/beat")
    # Vocal presence disabled — see compas_core/analyze.py for why.
    # if header == "Vocal":
    #     if a.vocal_source == "title":
    #         return _wrap("This track: the filename says 'instrumental', so "
    #                      f"that was used. The audio scored "
    #                      f"{a.vocal_score:.1f}.")
    #     return _wrap(f"This track: score {a.vocal_score:.1f}, singing over "
    #                  f"{a.vocal_fraction*100:.0f}% of the track, confidence "
    #                  f"{a.vocal_confidence:.2f}")
    return None


class TrackSortProxy(QSortFilterProxyModel):
    """Sorts on Qt.UserRole, sinks unanalyzed rows, and filters the list.

    Missing values are stored as magic lows (-1 for most metrics, -999 for
    LUFS, -1 for facet levels), so an *ascending* sort on any metric used to
    open with a screenful of blank rows — during a partial run that is every
    track still queued, i.e. most of them. Sinking them instead means the
    numbers you sorted for are the ones at the top, in both directions.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSortRole(Qt.UserRole)
        self._needle = ""
        self._failed_only = False

    # --- filtering ---------------------------------------------------------
    def set_needle(self, text: str) -> None:
        needle = text.strip().lower()
        if needle != self._needle:
            self._needle = needle
            self.invalidateFilter()

    def set_failed_only(self, on: bool) -> None:
        if on != self._failed_only:
            self._failed_only = on
            self.invalidateFilter()

    def is_filtered(self) -> bool:
        return bool(self._needle) or self._failed_only

    def filterAcceptsRow(self, source_row: int, parent=QModelIndex()) -> bool:
        model = self.sourceModel()
        if model is None or not 0 <= source_row < len(model.rows):
            # Reached transiently while the source model is resetting.
            return False
        if self._failed_only and model.rows[source_row].status != "error":
            return False
        if not self._needle:
            return True
        return self._needle in model.search_text(source_row)

    def lessThan(self, left, right) -> bool:
        model = self.sourceModel()
        column = model.columns[left.column()]
        if column.sinks_pending:
            l_empty = model.rows[left.row()].analysis is None
            r_empty = model.rows[right.row()].analysis is None
            if l_empty != r_empty:
                # Inverted for a descending sort, since Qt reverses the result
                # — otherwise "pending last" would just become "pending first"
                # the moment the header was clicked twice.
                return l_empty == (self.sortOrder() == Qt.DescendingOrder)
        return super().lessThan(left, right)


class TrackTableModel(QAbstractTableModel):
    def __init__(self, axis_keys=facets.DEFAULT_AXIS_KEYS,
                 vocabulary: str = facets.ENGLISH) -> None:
        super().__init__()
        self.rows: list[TrackRow] = []
        self.axis_keys = tuple(axis_keys)
        self.vocabulary = vocabulary
        self.columns = build_columns(self.axis_keys, self.vocabulary)

    # --- facet configuration ----------------------------------------------
    def set_facets(self, axis_keys, vocabulary: str) -> None:
        self.beginResetModel()
        self.axis_keys = tuple(axis_keys)
        self.vocabulary = vocabulary
        self.columns = build_columns(self.axis_keys, self.vocabulary)
        self.endResetModel()

    # --- Qt plumbing -----------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal or not 0 <= section < len(self.columns):
            return None
        if role == Qt.DisplayRole:
            return self.columns[section].label
        if role == Qt.ToolTipRole:
            column = self.columns[section]
            # An abbreviated header has to say what it stands for, above the
            # explanation of what it measures.
            if column.short:
                return f"{column.header}\n\n{column.tooltip}".strip()
            return column.tooltip or None
        # Numeric cells are right-aligned; without this the header sits to
        # the left of its own column of numbers.
        if role == Qt.TextAlignmentRole and self.columns[section].numeric:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        column = self.columns[index.column()]
        if role == Qt.DisplayRole:
            return column.display(row)
        if role == Qt.UserRole:
            return column.sort(row)
        if role == Qt.TextAlignmentRole and column.numeric:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.BackgroundRole and row.analysis is not None:
            return _RHYTHM_COLORS.get(row.analysis.rhythm)
        if role == Qt.ForegroundRole and column.header == "Status":
            return _STATUS_COLORS.get(row.status)
        if role == Qt.ToolTipRole:
            if column.header == "Status" and row.status == "error":
                return _wrap(row.error)
            # The one-line summary, not the full essay: the header carries the
            # long form, and this fires on every cell the mouse crosses while
            # the user is comparing numbers across twenty columns.
            parts = [column.summary or column.tooltip,
                     _cell_note(row, column.header)]
            return "\n\n".join(p for p in parts if p) or None
        return None

    # --- filtering ----------------------------------------------------------
    def search_text(self, i: int) -> str:
        """Lowercase haystack for the filter box.

        Only the columns worth typing at — the filename, the rhythm, the key,
        the status and every facet reading. Numbers are left out: a search for
        "44" that matches Sync, Artic and a year in the filename is noise.
        Includes the error message, so filtering on "ffmpeg" finds the rows
        that failed for that reason.
        """
        row = self.rows[i]
        parts = [c.display(row) for c in self.columns if c.searchable]
        if row.error:
            parts.append(row.error)
        return " ".join(parts).lower()

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
                self.index(i, 0), self.index(i, len(self.columns) - 1))
