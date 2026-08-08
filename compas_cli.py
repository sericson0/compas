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
    ap.add_argument("--csv", metavar="FILE", help="Write results as CSV")
    ap.add_argument("--json", metavar="FILE", help="Write results as JSON")
    ap.add_argument("--write-tags", action="store_true",
                    help="Write BPM/INITIALKEY/COMPAS_* tags into the files")
    ap.add_argument("--key-format", default="standard",
                    choices=["standard", "camelot"],
                    help="INITIALKEY format when writing tags")
    args = ap.parse_args()

    from compas_core import analyze_file
    from compas_core.tags import write_tags

    files = collect_files(args.paths)
    if not files:
        print("No audio files found.", file=sys.stderr)
        return 1

    results = []
    hdr = (f"{'file':<44} {'rhythm':<8} {'src':<10} {'bpm':>6} {'range':>9} "
           f"{'bars/m':>6} {'stab':>5} {'time':<8} {'key':>4} {'cam':>3} "
           f"{'enrg':>4} {'drv':>4} {'dyn':>5}")
    print(hdr)
    print("-" * len(hdr))

    for f in files:
        try:
            r = analyze_file(f, rhythm=args.rhythm)
        except Exception:
            print(f"{f.name[:44]:<44} ERROR")
            traceback.print_exc()
            continue
        results.append(r)
        print(
            f"{r.filename[:44]:<44} {r.rhythm:<8} {r.rhythm_source:<10} "
            f"{r.bpm:>6.1f} {f'{r.bpm_low:.0f}-{r.bpm_high:.0f}':>9} "
            f"{r.bars_per_min:>6.1f} {r.stability:>5.0f} {r.timing:<8} "
            f"{r.key:>4} {r.camelot:>3} {r.energy:>4.1f} {r.drive:>4.0f} "
            f"{r.dynamic_range_db:>5.1f}"
        )
        if args.write_tags:
            write_tags(r.path, r.tag_fields(
                key_as_camelot=(args.key_format == "camelot")))

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
