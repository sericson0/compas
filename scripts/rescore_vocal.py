"""Recompute only the vocal columns of an existing library CSV.

Tuning the vocal detector should not cost a full re-analysis. Everything it
needs beyond the audio is the tempo, and that is already in the CSV, so
rescoring 12,000 tracks takes about twenty minutes instead of six hours.

    python scripts/rescore_vocal.py library.csv
    python scripts/rescore_vocal.py library.csv --out rescored.csv --workers 6

Rewrites vocal, vocal_source, vocal_score, vocal_fraction and
vocal_confidence in place (via a temporary file), leaving every other
column untouched. Rows whose audio is missing keep their old values and are
reported.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compas_core.audio import load_audio  # noqa: E402
from compas_core.vocal import analyze_vocal, vocal_hint_from_name  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

VOCAL_COLUMNS = ("vocal", "vocal_source", "vocal_score", "vocal_fraction",
                 "vocal_confidence")


def rescore(row: dict) -> dict:
    path = Path(row["path"])
    if not path.exists():
        return row
    try:
        y, sr = load_audio(path)
        result = analyze_vocal(
            y, sr, float(row["bpm"]),
            instrumental_hint=vocal_hint_from_name(
                row.get("filename"), row.get("title")))
    except Exception as exc:  # noqa: BLE001 — keep the old values
        print(f"  ERROR {path.name[:60]}: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return row
    row["vocal"] = result.vocal
    row["vocal_source"] = result.vocal_source
    row["vocal_score"] = f"{result.vocal_score}"
    row["vocal_fraction"] = f"{result.vocal_fraction}"
    row["vocal_confidence"] = f"{result.vocal_confidence}"
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="Library CSV from scripts/analyze_library.py")
    ap.add_argument("--out", default=None,
                    help="Write here instead of updating in place")
    ap.add_argument("--workers", type=int,
                    default=max(1, min(6, (os.cpu_count() or 4) - 2)))
    args = ap.parse_args()

    src = Path(args.csv)
    with open(src, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    missing = [c for c in (*VOCAL_COLUMNS, "path", "bpm")
               if c not in fieldnames]
    if missing:
        print(f"CSV is missing required columns: {missing}", file=sys.stderr)
        if any(c.startswith("vocal") for c in missing):
            print("\nVocal presence is currently DISABLED in "
                  "compas_core/analyze.py, so\nlibrary CSVs no longer carry "
                  "vocal_* columns. Re-enable it there (see the\nnote on "
                  "TrackAnalysis) and re-run the analysis, or use\n"
                  "scripts/validate_vocal.py against an audio folder, which "
                  "calls the\ndetector directly.", file=sys.stderr)
        return 1

    print(f"{len(rows)} rows, {args.workers} workers")
    started = time.perf_counter()
    absent = sum(1 for r in rows if not Path(r["path"]).exists())
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        out_rows = []
        for row in pool.map(rescore, rows):
            out_rows.append(row)
            done += 1
            if done % 250 == 0 or done == len(rows):
                rate = done / (time.perf_counter() - started)
                print(f"  {done}/{len(rows)}  {rate:.2f} tracks/s  "
                      f"eta {int((len(rows)-done)/max(rate,1e-9)/60)}m",
                      flush=True)

    dest = Path(args.out) if args.out else src
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames,
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)
    tmp.replace(dest)

    elapsed = time.perf_counter() - started
    print(f"\nRescored {len(rows) - absent} of {len(rows)} in "
          f"{elapsed/60:.1f} min -> {dest}")
    if absent:
        print(f"{absent} row(s) kept their old values (audio not found)")
    print("Now re-fit the threshold:  python scripts/validate_vocal.py "
          f"{dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
