"""Compare COMPAS batch results (CSV) against Mixed-In-Key tags in the files.

BPM agreement is checked modulo the metrical-level factors (1, 2, 3, 1/2,
1/3, 4/3, 3/2, ...) since MIK and COMPAS may count different levels; what
matters is that the two are metrically consistent, and which factor links
them is reported.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import mutagen

FACTORS = {
    "1": 1.0, "2": 2.0, "1/2": 0.5, "3": 3.0, "1/3": 1 / 3,
    "4/3": 4 / 3, "3/4": 0.75, "3/2": 1.5, "2/3": 2 / 3, "4": 4.0,
}


def main(csv_path: str) -> None:
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    print(f"{'file':<46} {'mik_bpm':>8} {'ours':>6} {'factor':>6} "
          f"{'mik_key':>7} {'ours':>5} {'stab':>4}")
    for r in rows:
        mf = mutagen.File(r["path"])
        mik_bpm = (mf.get("bpm") or [""])[0]
        mik_key = (mf.get("initialkey") or [""])[0]
        ours = float(r["bpm"])
        factor_lbl = ""
        if mik_bpm and float(mik_bpm) > 0:
            mik = float(mik_bpm)
            best = min(FACTORS.items(),
                       key=lambda kv: abs(ours / (mik * kv[1]) - 1))
            rel_err = abs(ours / (mik * best[1]) - 1)
            factor_lbl = f"x{best[0]}" if rel_err < 0.04 else "MISMATCH"
        print(f"{Path(r['path']).name[:46]:<46} {mik_bpm or '-':>8} "
              f"{ours:>6.1f} {factor_lbl:>6} {mik_key or '-':>7} "
              f"{r['key']:>5} {float(r['stability']):>4.0f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "scratch_results.csv")
