"""Score the vocal detector against filename ground truth, and re-fit it.

Ground truth comes free from a library that already marks instrumentals in
the title -- "Laurenz - Milonga De Mis Amores - Instrumental - 1944.flac".
Anything without that word counts as vocal, which is the weak half of the
labelling: an unmarked instrumental is a mislabelled positive, not a
detector error. Check the reported misses before believing the number.

Usage:
    python scripts/validate_vocal.py example_songs
    python scripts/validate_vocal.py library.csv        # from compas_cli --csv
    python scripts/validate_vocal.py my_library --fast --limit 400

The CSV path is the one to use on a real library: run the analysis once
(``python compas_cli.py my_library --fast --csv library.csv``) and re-fit
from the export as often as you like.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compas_core.vocal import (  # noqa: E402
    ESTRIBILLO_MAX_FRACTION,
    VOCAL_THRESHOLD,
    vocal_hint_from_name,
)

AUDIO_EXTS = {".flac", ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".aiff", ".wma"}

# Tango filenames are full of accents (Falcón, Galé, Durán) and the Windows
# console defaults to cp1252, which cannot encode them. Without this, simply
# printing a miss list kills the script.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def rows_from_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        raw = list(csv.DictReader(fh))
    out = []
    for r in raw:
        if not r.get("vocal_score"):
            continue
        name = r.get("filename") or Path(r.get("path", "")).name
        out.append(dict(name=name, score=float(r["vocal_score"]),
                        fraction=float(r.get("vocal_fraction") or 0.0),
                        truth="instr" if vocal_hint_from_name(
                            name, r.get("title")) else "vocal"))
    return out


def rows_from_folder(folder: Path, fast: bool, limit: int | None) -> list[dict]:
    from compas_core import analyze_file

    files = sorted(f for f in folder.rglob("*") if f.suffix.lower() in AUDIO_EXTS)
    if limit:
        files = files[:limit]
    out = []
    for i, f in enumerate(files, 1):
        try:
            a = analyze_file(f, fast=fast)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{i}/{len(files)}] ERROR {f.name}: {exc}", file=sys.stderr)
            continue
        out.append(dict(name=f.name, score=a.vocal_score,
                        fraction=a.vocal_fraction,
                        truth="instr" if vocal_hint_from_name(f.name, a.title)
                        else "vocal"))
        print(f"  [{i}/{len(files)}] {f.name[:56]:<56} "
              f"{out[-1]['score']:6.1f}  {out[-1]['truth']}")
    return out


def sweep(rows: list[dict]) -> tuple[float, float]:
    """Best single threshold and the accuracy it reaches."""
    inst = [r["score"] for r in rows if r["truth"] == "instr"]
    voc = [r["score"] for r in rows if r["truth"] == "vocal"]
    if not inst or not voc:
        return VOCAL_THRESHOLD, 0.0
    best_t, best_acc = VOCAL_THRESHOLD, 0.0
    for th in np.linspace(min(inst + voc), max(inst + voc), 2000):
        acc = (sum(x < th for x in inst) + sum(x >= th for x in voc)) / len(rows)
        if acc > best_acc:
            best_acc, best_t = acc, float(th)
    return best_t, best_acc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target", help="Audio folder, or a CSV from compas_cli")
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    target = Path(args.target)
    if target.suffix.lower() == ".csv":
        rows = rows_from_csv(target)
    elif target.is_dir():
        rows = rows_from_folder(target, args.fast, args.limit)
    else:
        print(f"Not a folder or CSV: {target}", file=sys.stderr)
        return 1
    if not rows:
        print("Nothing to score.", file=sys.stderr)
        return 1

    inst = [r["score"] for r in rows if r["truth"] == "instr"]
    voc = [r["score"] for r in rows if r["truth"] == "vocal"]
    n = len(rows)
    base = max(len(inst), len(voc)) / n

    print(f"\n{n} tracks — {len(inst)} marked instrumental, {len(voc)} not.")
    print(f"Base rate to beat (always guess the larger class): {base*100:.0f}%")
    if not inst or not voc:
        print("Need both classes present to score.", file=sys.stderr)
        return 1

    sd = float(np.sqrt((np.var(inst) + np.var(voc)) / 2))
    d = (float(np.mean(voc)) - float(np.mean(inst))) / max(sd, 1e-9)
    print(f"\n  instrumental  mean {np.mean(inst):6.2f}  "
          f"[{min(inst):6.2f}, {max(inst):6.2f}]")
    print(f"  vocal         mean {np.mean(voc):6.2f}  "
          f"[{min(voc):6.2f}, {max(voc):6.2f}]")
    print(f"  separation d' {d:+.2f}")

    best_t, best_acc = sweep(rows)
    cur_acc = (sum(x < VOCAL_THRESHOLD for x in inst)
               + sum(x >= VOCAL_THRESHOLD for x in voc)) / n
    print(f"\n  current VOCAL_THRESHOLD = {VOCAL_THRESHOLD:.2f} "
          f"-> {cur_acc*100:.1f}% ({round(cur_acc*n)}/{n})")
    print(f"  best threshold          = {best_t:.2f} "
          f"-> {best_acc*100:.1f}% ({round(best_acc*n)}/{n})")

    tp = sum(1 for r in rows if r["truth"] == "vocal" and r["score"] >= best_t)
    fp = sum(1 for r in rows if r["truth"] == "instr" and r["score"] >= best_t)
    fn = sum(1 for r in rows if r["truth"] == "vocal" and r["score"] < best_t)
    print(f"  at that threshold: precision {tp/max(tp+fp,1)*100:5.1f}%  "
          f"recall {tp/max(tp+fn,1)*100:5.1f}%")

    print(f"\n  suggested edit in compas_core/vocal.py:")
    print(f"      VOCAL_THRESHOLD = {best_t:.1f}")
    print(f"  (ESTRIBILLO_MAX_FRACTION is {ESTRIBILLO_MAX_FRACTION}; it needs "
          f"labelled\n   refrains to fit, which filenames do not provide.)")

    misses = [r for r in rows
              if (r["truth"] == "instr") != (r["score"] < best_t)]
    if misses:
        print(f"\n  {len(misses)} miss(es) at the best threshold:")
        for r in sorted(misses, key=lambda r: r["score"]):
            print(f"    {r['score']:6.2f}  labelled {r['truth']:<6} "
                  f"{r['name'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
