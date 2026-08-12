"""Analyse a whole library into a CSV, resumably.

``compas_cli.py`` is a single-threaded loop that holds every result in
memory and writes the CSV at the end. That is fine for a folder and wrong
for a discography: a twelve-thousand-file run takes hours, and losing all
of it to one interruption at track 11,000 is not a risk worth taking.

This runner writes each row as it completes, skips anything already in the
CSV, and keeps going past individual failures.

    python scripts/analyze_library.py "D:\\Tango" --csv library.csv --fast
    python scripts/analyze_library.py "D:\\Tango" --csv library.csv --fast
        # ^ run it again after an interruption; it picks up where it stopped

Then calibrate:

    python scripts/calibrate_facets.py library.csv --per-rhythm
    python scripts/validate_vocal.py library.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compas_core.analyze import TrackAnalysis, analyze_file  # noqa: E402

AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".aiff", ".wma"}
FIELDNAMES = [f.name for f in fields(TrackAnalysis)]

# Accented filenames (Falcón, Galé, Durán) are everywhere in a tango
# library and the Windows console is cp1252. Reporting one failed file must
# not be able to kill a six-hour run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def collect(root: Path) -> list[Path]:
    # "._name.m4a" is a macOS AppleDouble resource fork, not audio: it has
    # the extension and none of the contents, so ffmpeg reports a missing
    # moov atom. A library copied from a Mac is full of them.
    return sorted(p for p in root.rglob("*")
                  if p.suffix.lower() in AUDIO_EXTS
                  and not p.name.startswith("._"))


def already_done(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    try:
        with open(csv_path, newline="", encoding="utf-8") as fh:
            return {r["path"] for r in csv.DictReader(fh) if r.get("path")}
    except (OSError, KeyError, csv.Error):
        return set()


def fmt(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", help="Library folder")
    ap.add_argument("--csv", required=True, help="Output CSV (appended to)")
    ap.add_argument("--fast", action="store_true",
                    help="Skip harmonic separation — ~4x faster. Recommended "
                         "for a library run; only Key/Camelot/Harmony differ.")
    ap.add_argument("--rhythm", default="auto",
                    choices=["auto", "tango", "vals", "milonga"])
    ap.add_argument("--workers", type=int,
                    default=max(1, min(4, (os.cpu_count() or 4) - 1)),
                    help="Parallel tracks (librosa saturates cores per track, "
                         "so more than 4 buys little)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after this many new tracks (for a trial run)")
    ap.add_argument("--no-resume", action="store_true",
                    help="Re-analyse everything, overwriting the CSV")
    ap.add_argument("--no-shuffle", action="store_true",
                    help="Analyse in path order instead of shuffled")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f"Not a folder: {root}", file=sys.stderr)
        return 1
    csv_path = Path(args.csv)
    errors_path = csv_path.with_suffix(".errors.log")

    files = collect(root)
    done = set() if args.no_resume else already_done(csv_path)
    todo = [f for f in files if str(f) not in done]
    if not args.no_shuffle:
        # Shuffled, so any *prefix* of the CSV is a representative sample of
        # the library rather than everything alphabetically before "Canaro".
        # On a run measured in hours that is what makes it possible to
        # calibrate off partial results instead of waiting for the end.
        # Fixed seed: same library, same order, so a resumed run is stable.
        random.Random(20260811).shuffle(todo)
    if args.limit:
        todo = todo[: args.limit]

    print(f"{len(files)} audio files under {root}")
    if done:
        print(f"{len(done)} already in {csv_path} — resuming")
    print(f"{len(todo)} to analyse, {args.workers} workers, "
          f"{'fast' if args.fast else 'default'} mode")
    if not todo:
        print("Nothing to do.")
        return 0

    fresh = args.no_resume or not csv_path.exists()
    mode = "w" if fresh else "a"
    started = time.perf_counter()
    n_ok = n_err = 0

    with open(csv_path, mode, newline="", encoding="utf-8") as out, \
            open(errors_path, "a", encoding="utf-8") as errlog:
        writer = csv.DictWriter(out, fieldnames=FIELDNAMES,
                                extrasaction="ignore")
        if fresh:
            writer.writeheader()

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(analyze_file, f, args.rhythm, args.fast): f
                for f in todo
            }
            for i, future in enumerate(as_completed(futures), 1):
                path = futures[future]
                try:
                    writer.writerow(future.result().to_dict())
                    n_ok += 1
                except Exception as exc:  # noqa: BLE001 — one bad file
                    n_err += 1
                    errlog.write(f"{path}\n{traceback.format_exc()}\n")
                    errlog.flush()
                    print(f"  ERROR {path.name[:60]}: "
                          f"{type(exc).__name__}: {exc}", file=sys.stderr)

                if i % 25 == 0 or i == len(todo):
                    out.flush()
                    elapsed = time.perf_counter() - started
                    rate = i / elapsed
                    eta = (len(todo) - i) / rate if rate else 0
                    print(f"  {i}/{len(todo)}  {rate:.2f} tracks/s  "
                          f"elapsed {fmt(elapsed)}  eta {fmt(eta)}  "
                          f"errors {n_err}", flush=True)

    elapsed = time.perf_counter() - started
    print(f"\nDone: {n_ok} analysed, {n_err} failed, in {fmt(elapsed)} "
          f"({elapsed/max(n_ok+n_err,1):.2f} s/track wall clock)")
    print(f"CSV: {csv_path}")
    if n_err:
        print(f"Errors logged to {errors_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
