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

# Tango filenames carry accents and the occasional non-breaking hyphen, and
# a redirected stdout on Windows is cp1252. Without this, printing one
# filename kills a run that may be hours in. Every script under scripts/
# guards this the same way.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _is_audio(p: Path) -> bool:
    # "._name.m4a" is a macOS AppleDouble resource fork, not audio.
    return p.suffix.lower() in AUDIO_EXTS and not p.name.startswith("._")


def collect_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files.extend(sorted(f for f in path.rglob("*") if _is_audio(f)))
        elif path.is_file():
            if not _is_audio(path):
                print(f"warning: {p} is not an audio file, skipping",
                      file=sys.stderr)
                continue
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
    # The GUI's Write tags dialog has always let you leave BPM and key alone;
    # the CLI overwrote both unconditionally, which is the destructive half of
    # the operation and the half a Mixed In Key library wants to keep.
    ap.add_argument("--no-bpm", action="store_true",
                    help="With --write-tags: leave the BPM tag untouched")
    ap.add_argument("--no-key", action="store_true",
                    help="With --write-tags: leave the INITIALKEY tag "
                         "untouched")
    ap.add_argument("--no-compas", action="store_true",
                    help="With --write-tags: skip the COMPAS_* fields")
    ap.add_argument("--comment", action="store_true",
                    help="With --write-tags: append \"COMPAS Energy N\" to "
                         "the comment, keeping the existing text")
    ap.add_argument("--key-format", default="standard",
                    choices=["standard", "camelot"],
                    help="INITIALKEY format when writing tags")
    ap.add_argument("--facets", default="english",
                    choices=["english", "tango", "off"],
                    help="Vocabulary for the composed facet label")
    ap.add_argument("--facet-axes", default=None,
                    help="Comma-separated axis keys for the facet label "
                         "(default: tempo,drive,timing). "
                         "Use --list-axes to see them all.")
    ap.add_argument("--list-axes", action="store_true",
                    help="List the available facet axes and exit")
    args = ap.parse_args()

    from compas_core import analyze_file, facets
    from compas_core.analyze import RHYTHM_CONFIDENCE_FLOOR
    from compas_core.tags import append_energy_comment, write_tags

    if (args.no_bpm and args.no_key and args.no_compas and not args.comment
            and args.write_tags):
        print("--write-tags with every field disabled would write nothing.",
              file=sys.stderr)
        return 1

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
    if not axis_keys:
        # An empty axis list composes to the empty string, and writing that
        # would store a blank COMPAS_FACETS in every file.
        vocabulary = None

    files = collect_files(args.paths)
    if not files:
        print("No audio files found.", file=sys.stderr)
        return 1

    results = []
    tag_errors: list[str] = []
    n_failed = 0
    hdr = (f"{'file':<42} {'rhythm':<16} {'bpm':>6} {'stab':>5} {'key':>4} "
           f"{'enrg':>4} {'drv':>4} {'sync':>4} {'art':>4} {'tex':>4} "
           f"{'harm':>4} {'LUFS':>6} {'LRA':>5}")
    if vocabulary:
        hdr += "  facets"
    print(hdr)
    print("-" * len(hdr))

    for f in files:
        try:
            r = analyze_file(f, rhythm=args.rhythm, fast=args.fast)
        except Exception:
            n_failed += 1
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
        line = (
            f"{r.filename[:42]:<42} {rhythm_col:<16} {r.bpm:>6.1f} "
            f"{r.stability:>5.0f} {r.key:>4} {r.energy:>4.1f} "
            f"{r.drive:>4.0f} {r.syncopation:>4.0f} {r.articulation:>4.0f} "
            f"{r.percussiveness:>4.0f} {r.harmonic_variety:>4.0f} "
            f"{lufs:>6} {lra:>5}"
        )
        if vocabulary:
            line += "  " + r.facet_label(vocabulary, axis_keys)
        print(line)
        if args.write_tags:
            # Inside its own guard: one unwritable file must not abort a run
            # whose CSV is only written at the end.
            try:
                write_tags(
                    r.path,
                    r.tag_fields(
                        key_as_camelot=(args.key_format == "camelot"),
                        facet_vocabulary=vocabulary, facet_axes=axis_keys),
                    write_bpm=not args.no_bpm,
                    write_key=not args.no_key,
                    write_compas=not args.no_compas,
                )
                if args.comment:
                    append_energy_comment(r.path, r.energy)
            except Exception as exc:  # noqa: BLE001 — report and continue
                tag_errors.append(f"{r.filename}: {exc}")

    if not results:
        # Exiting 0 here would tell any wrapper or scheduled run that a
        # total failure succeeded.
        print(f"\nNo files could be analyzed ({n_failed} failed).",
              file=sys.stderr)
        for flag in ("csv", "json"):
            if getattr(args, flag):
                print(f"{flag.upper()} not written: nothing to write.",
                      file=sys.stderr)
        return 1

    if args.csv:
        try:
            with open(args.csv, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(
                    fh, fieldnames=list(results[0].to_dict().keys()))
                w.writeheader()
                w.writerows(r.to_dict() for r in results)
            print(f"\nCSV written: {args.csv}")
        except OSError as exc:
            print(f"\nCould not write CSV {args.csv}: {exc}", file=sys.stderr)
            return 1

    if args.json:
        try:
            Path(args.json).write_text(
                json.dumps([r.to_dict() for r in results], indent=2),
                encoding="utf-8")
            print(f"JSON written: {args.json}")
        except OSError as exc:
            print(f"Could not write JSON {args.json}: {exc}", file=sys.stderr)
            return 1

    if n_failed:
        print(f"\n{n_failed} file(s) failed to analyze.", file=sys.stderr)
    if tag_errors:
        print(f"\n{len(tag_errors)} file(s) could not be tagged:",
              file=sys.stderr)
        for line in tag_errors[:15]:
            print(f"  {line}", file=sys.stderr)
        if len(tag_errors) > 15:
            print(f"  … and {len(tag_errors) - 15} more", file=sys.stderr)

    return 1 if (n_failed or tag_errors) else 0


if __name__ == "__main__":
    sys.exit(main())
