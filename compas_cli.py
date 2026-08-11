"""COMPAS command-line interface: batch analysis, reports, optional tag writing.

Examples:
    python compas_cli.py example_songs
    python compas_cli.py example_songs --rhythm auto --csv results.csv
    python compas_cli.py song.flac --write-tags --key-format camelot
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from pathlib import Path

AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".aiff", ".wma"}


def collect_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(
                f for f in path.rglob("*") if f.suffix.lower() in AUDIO_EXTS
            ))
        elif path.is_file():
            files.append(path)
        else:
            print(f"warning: {p} not found", file=sys.stderr)
    return files


def main() -> int:
    ap = argparse.ArgumentParser(prog="compas", description=__doc__)
    ap.add_argument("paths", nargs="+", help="Audio files and/or folders")
    ap.add_argument("--rhythm", default="auto",
                    choices=["auto", "tango", "vals", "milonga"],
                    help="Song type; auto = GENRE tag, then audio heuristic")
    ap.add_argument("--fast", action="store_true",
                    help="Skip harmonic separation (~4x faster; affects only "
                         "the key estimate)")
    ap.add_argument("--csv", metavar="FILE", help="Write results as CSV")
    ap.add_argument("--json", metavar="FILE", help="Write results as JSON")
    ap.add_argument("--write-tags", action="store_true",
                    help="Write BPM/INITIALKEY/COMPAS_* tags into the files")
    ap.add_argument("--key-format", default="standard",
                    choices=["standard", "camelot"],
                    help="INITIALKEY format when writing tags")
    ap.add_argument("--facets", default="english",
                    choices=["english", "tango", "off"],
                    help="Vocabulary for the composed facet label")
    ap.add_argument("--facet-axes", default=None,
                    help="Comma-separated axis keys for the facet label "
                         "(default: tempo,drive,timing,vocal). "
                         "Use --list-axes to see them all.")
    ap.add_argument("--list-axes", action="store_true",
                    help="List the available facet axes and exit")
    args = ap.parse_args()

    from compas_core import analyze_file, facets
    from compas_core.analyze import RHYTHM_CONFIDENCE_FLOOR
    from compas_core.tags import write_tags

    if args.list_axes:
        print("Facet axes (* = on by default):\n")
        for axis in facets.AXES:
            mark = "*" if axis.default else " "
            en = " / ".join(axis.labels[facets.ENGLISH])
            tg = " / ".join(axis.labels[facets.TANGO])
            print(f" {mark} {axis.key:<13} {axis.name}")
            print(f"     english  {en}")
            print(f"     tango    {tg}")
        return 0

    vocabulary = None if args.facets == "off" else args.facets
    axis_keys = (tuple(k.strip() for k in args.facet_axes.split(",") if k.strip())
                 if args.facet_axes else facets.DEFAULT_AXIS_KEYS)
    unknown = [k for k in axis_keys if k not in facets.AXES_BY_KEY]
    if unknown:
        print(f"Unknown facet axes: {', '.join(unknown)}. "
              f"Use --list-axes.", file=sys.stderr)
        return 1

    files = collect_files(args.paths)
    if not files:
        print("No audio files found.", file=sys.stderr)
        return 1

    results = []
    hdr = (f"{'file':<42} {'rhythm':<16} {'bpm':>6} {'stab':>5} {'key':>4} "
           f"{'enrg':>4} {'drv':>4} {'sync':>4} {'art':>4} {'tex':>4} "
           f"{'harm':>4} {'voice':<14} {'LUFS':>6} {'LRA':>5}")
    if vocabulary:
        hdr += "  facets"
    print(hdr)
    print("-" * len(hdr))

    for f in files:
        try:
            r = analyze_file(f, rhythm=args.rhythm, fast=args.fast)
        except Exception:
            print(f"{f.name[:44]:<44} ERROR")
            traceback.print_exc()
            continue
        results.append(r)
        src = r.rhythm_source
        if src == "audio" and r.rhythm_confidence < RHYTHM_CONFIDENCE_FLOOR:
            src += "?"
        rhythm_col = f"{r.rhythm} ({src})"
        lufs = f"{r.lufs:.1f}" if r.lufs is not None else "-"
        lra = f"{r.lra:.1f}" if r.lra is not None else "-"
        # "tag" = the filename said so; "?" = a shaky audio guess.
        voice = r.vocal + (" (tag)" if r.vocal_source == "title"
                           else " ?" if r.vocal_confidence < 0.25 else "")
        line = (
            f"{r.filename[:42]:<42} {rhythm_col:<16} {r.bpm:>6.1f} "
            f"{r.stability:>5.0f} {r.key:>4} {r.energy:>4.1f} "
            f"{r.drive:>4.0f} {r.syncopation:>4.0f} {r.articulation:>4.0f} "
            f"{r.percussiveness:>4.0f} {r.harmonic_variety:>4.0f} "
            f"{voice:<14} {lufs:>6} {lra:>5}"
        )
        if vocabulary:
            line += "  " + r.facet_label(vocabulary, axis_keys)
        print(line)
        if args.write_tags:
            write_tags(r.path, r.tag_fields(
                key_as_camelot=(args.key_format == "camelot"),
                facet_vocabulary=vocabulary, facet_axes=axis_keys))

    if args.csv and results:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(results[0].to_dict().keys()))
            w.writeheader()
            w.writerows(r.to_dict() for r in results)
        print(f"\nCSV written: {args.csv}")

    if args.json and results:
        Path(args.json).write_text(
            json.dumps([r.to_dict() for r in results], indent=2),
            encoding="utf-8")
        print(f"JSON written: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
