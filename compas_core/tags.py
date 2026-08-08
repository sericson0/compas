"""Read and write file tags via mutagen.

Reading: pull the fields used for display and rhythm auto-detection.
Writing: standard fields (BPM, INITIALKEY) that VirtualDJ and other DJ
software import from tags, plus COMPAS_* custom fields for everything else.
Writing only ever happens on explicit user request, never during analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FileTags:
    genre: str | None = None
    artist: str | None = None
    title: str | None = None
    date: str | None = None
    existing_bpm: str | None = None   # BPM already in the tags (MIK/Serato/…)
    existing_key: str | None = None   # initial key already in the tags


def _existing_analysis(path: str) -> tuple[str | None, str | None]:
    """Existing BPM / initial-key tags from other tools, if any."""
    import mutagen
    from mutagen.id3 import ID3FileType
    from mutagen.mp4 import MP4

    try:
        raw = mutagen.File(path)
    except Exception:
        return None, None
    if raw is None or not raw.tags:
        return None, None

    def first(container, key):
        try:
            vals = container.get(key)
        except Exception:
            return None
        if not vals:
            return None
        val = vals[0] if isinstance(vals, (list, tuple)) else vals
        text = str(getattr(val, "text", [val])[0] if hasattr(val, "text") else val)
        return text.strip() or None

    if isinstance(raw, MP4):
        bpm = first(raw.tags, "tmpo")
        key = first(raw.tags, "----:com.apple.iTunes:initialkey")
        if key is not None:
            key = key.strip("b'\"")
        return bpm, key
    if isinstance(raw, ID3FileType):
        return first(raw.tags, "TBPM"), first(raw.tags, "TKEY")
    # Vorbis-comment style (FLAC/OGG): case-insensitive flat keys
    return first(raw, "bpm"), first(raw, "initialkey")


def read_tags(path: str | Path) -> FileTags:
    import mutagen

    try:
        mf = mutagen.File(str(path), easy=True)
    except Exception:
        return FileTags()
    if mf is None or not mf.tags:
        return FileTags()

    def first(key: str) -> str | None:
        vals = mf.tags.get(key)
        return str(vals[0]) if vals else None

    bpm, key = _existing_analysis(str(path))
    return FileTags(
        genre=first("genre"),
        artist=first("artist"),
        title=first("title"),
        date=first("date"),
        existing_bpm=bpm,
        existing_key=key,
    )


_ENERGY_MARK = re.compile(r"\s*(\||-)?\s*COMPAS Energy \d+(\.\d+)?", re.IGNORECASE)


def append_energy_comment(path: str | Path, energy: float) -> None:
    """Append/refresh a ``COMPAS Energy N`` note in the COMMENT tag.

    Never replaces the user's existing comment text — the marker is appended
    after it (Mixed-In-Key-style, so VirtualDJ users can browse energy from
    the comment column). A previous COMPAS marker is updated in place.
    """
    import mutagen
    from mutagen.flac import FLAC
    from mutagen.id3 import COMM, ID3
    from mutagen.mp4 import MP4

    note = f"COMPAS Energy {energy:g}"
    path = str(path)
    mf = mutagen.File(path)

    def merged(existing: str) -> str:
        base = _ENERGY_MARK.sub("", existing).rstrip()
        return f"{base} | {note}" if base else note

    if isinstance(mf, FLAC):
        existing = str(mf.get("COMMENT", [""])[0])
        mf["COMMENT"] = [merged(existing)]
        mf.save()
    elif isinstance(mf, MP4):
        existing = (mf.tags or {}).get("\xa9cmt", [""])
        mf["\xa9cmt"] = [merged(str(existing[0]) if existing else "")]
        mf.save()
    else:
        try:
            id3 = ID3(path)
        except Exception:
            id3 = ID3()
        frames = id3.getall("COMM")
        existing = str(frames[0].text[0]) if frames and frames[0].text else ""
        id3.setall("COMM", [COMM(encoding=3, lang="eng", desc="",
                                 text=[merged(existing)])])
        id3.save(path)


def write_tags(
    path: str | Path,
    fields: dict[str, str],
    *,
    write_bpm: bool = True,
    write_key: bool = True,
    write_compas: bool = True,
) -> None:
    """Write analysis results into the file's tags.

    ``fields`` uses canonical names: ``BPM``, ``INITIALKEY``, and any number
    of ``COMPAS_*`` entries. Format-specific mapping (ID3 frames, MP4 atoms)
    is handled here.
    """
    import mutagen
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3, TBPM, TKEY, TXXX
    from mutagen.mp4 import MP4

    path = str(path)
    mf = mutagen.File(path)
    if mf is None:
        raise RuntimeError(f"Unsupported file for tag writing: {path}")

    selected = {
        k: v for k, v in fields.items()
        if (k == "BPM" and write_bpm)
        or (k == "INITIALKEY" and write_key)
        or (k.startswith("COMPAS_") and write_compas)
        or (k == "COMMENT")
    }
    if not selected:
        return

    if isinstance(mf, FLAC) or hasattr(mf, "tags") and mf.tags.__class__.__name__ == "VCommentDict":
        # Vorbis comments (FLAC/OGG): flat key=value, exactly our canonical form
        for k, v in selected.items():
            mf[k] = [v]
        mf.save()
    elif isinstance(mf, MP4):
        for k, v in selected.items():
            if k == "BPM":
                mf["tmpo"] = [int(round(float(v)))]
            elif k == "INITIALKEY":
                mf["----:com.apple.iTunes:initialkey"] = [v.encode()]
            elif k == "COMMENT":
                mf["\xa9cmt"] = [v]
            else:
                mf[f"----:com.apple.iTunes:{k}"] = [v.encode()]
        mf.save()
    else:
        # Assume ID3 (MP3, AIFF, ...)
        try:
            id3 = ID3(path)
        except Exception:
            id3 = ID3()
        for k, v in selected.items():
            if k == "BPM":
                id3.setall("TBPM", [TBPM(encoding=3, text=[v])])
            elif k == "INITIALKEY":
                id3.setall("TKEY", [TKEY(encoding=3, text=[v])])
            else:
                id3.setall(f"TXXX:{k}", [TXXX(encoding=3, desc=k, text=[v])])
        id3.save(path)
