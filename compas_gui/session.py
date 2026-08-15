"""Autosave and restore of the track list and its results.

A default analysis of a 500-track library is around half an hour of work, and
until now every bit of it lived in RAM only: closing the window, or a crash,
threw the lot away without a word. The results are pure data — a TrackAnalysis
is a flat dataclass of numbers and strings, already JSON-serializable via
``to_dict()`` — so the whole session can be written out as each row finishes
and read back on the next launch.

What is *not* saved is anything derived: facet columns, the composed phrase and
every threshold are recomputed from the stored numbers, so a session written
before the thresholds were recalibrated shows the new readings on restore.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import MISSING, fields
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from compas_core.analyze import TrackAnalysis
from compas_gui.model import TrackRow

# Bumped when the on-disk shape changes incompatibly. A file with any other
# version is ignored rather than guessed at.
SCHEMA_VERSION = 1

_ANALYSIS_FIELDS = {f.name for f in fields(TrackAnalysis)}
# Fields with no default have to be present in the stored dict or the
# constructor call fails. Today that is all of them.
_REQUIRED_ANALYSIS_FIELDS = {
    f.name for f in fields(TrackAnalysis)
    if f.default is MISSING and f.default_factory is MISSING
}


def session_file() -> Path:
    """Where the session lives — per-user app data, not the project folder."""
    base = QStandardPaths.writableLocation(
        QStandardPaths.AppDataLocation) or tempfile.gettempdir()
    return Path(base) / "session.json"


def _row_to_dict(row: TrackRow) -> dict:
    # A row that was mid-flight when we saved is not a result; it comes back
    # as pending so Analyze picks it up again.
    status = row.status if row.status in ("done", "error") else "pending"
    return {
        "path": str(row.path),
        "status": status,
        "error": row.error if status == "error" else "",
        "rhythm_override": row.rhythm_override,
        "fast_mode": row.fast_mode,
        "analysis": row.analysis.to_dict() if row.analysis else None,
    }


def _analysis_from_dict(data: dict) -> TrackAnalysis | None:
    """Rebuild a TrackAnalysis, or None if the stored shape no longer fits.

    Fields COMPAS has since dropped are discarded and fields it has since
    gained make the row unrestorable — better to re-analyze one track than to
    show a row with a silently defaulted metric.
    """
    if not isinstance(data, dict):
        return None
    known = {k: v for k, v in data.items() if k in _ANALYSIS_FIELDS}
    if not _REQUIRED_ANALYSIS_FIELDS <= known.keys():
        return None
    try:
        return TrackAnalysis(**known)
    except (TypeError, ValueError):
        return None


def save(rows: list[TrackRow]) -> None:
    """Write the session, atomically. Never raises — this is a convenience."""
    target = session_file()
    payload = {
        "version": SCHEMA_VERSION,
        "tracks": [_row_to_dict(r) for r in rows],
    }
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-replace, so an interrupted save cannot leave a truncated
        # file that loses the session it was meant to protect.
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, target)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except (OSError, TypeError, ValueError):
        pass


def load() -> list[TrackRow]:
    """Restore the saved session, or [] if there is nothing usable."""
    target = session_file()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(payload, dict) or payload.get("version") != SCHEMA_VERSION:
        return []
    rows: list[TrackRow] = []
    for entry in payload.get("tracks") or ():
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        analysis = _analysis_from_dict(entry.get("analysis"))
        status = entry.get("status") or "pending"
        if status == "done" and analysis is None:
            # The numbers did not survive, so the row is not done any more.
            status = "pending"
        rows.append(TrackRow(
            path=Path(entry["path"]),
            status=status if status in ("pending", "done", "error") else "pending",
            error=entry.get("error") or "",
            rhythm_override=entry.get("rhythm_override") or "auto",
            fast_mode=bool(entry.get("fast_mode")),
            analysis=analysis,
        ))
    return rows


def clear() -> None:
    try:
        session_file().unlink()
    except OSError:
        pass
