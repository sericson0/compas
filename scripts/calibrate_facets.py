"""Re-fit facet thresholds (and metric anchors) from a real library.

Everything in ``compas_core/facets.py`` is currently cut to make a 19-track
example corpus fall into sensible groups. That is enough to ship a usable
feature and nowhere near enough to be right. Run a library through the CLI
once and this script will tell you what the cut points should actually be:

    python compas_cli.py D:\\Tango --fast --csv library.csv
    python scripts/calibrate_facets.py library.csv

By default it proposes tercile cuts (33rd/67th percentile), so each level
holds a third of the library. ``--split 20 80`` makes the outer levels
narrower, which is usually what you want for labels: most tracks read as
unremarkable and only the genuinely marked ones earn a word.

Percentiles are computed **within each rhythm** as well as overall, because
milonga and vals do not share a distribution with tango on most of these.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compas_core.facets import AXES  # noqa: E402
from compas_core.rhythm import RHYTHM_SPECS, Rhythm  # noqa: E402

# Metric anchors that map a raw measurement onto 0-100. If a library's raw
# values cluster inside a narrow part of the anchor range, the 0-100 score
# wastes most of its resolution and the facet cuts get twitchy.
RAW_ANCHORS = {
    "raw_attack_db": ("texture.ATTACK_ANCHORS", (2.5, 9.0)),
    "raw_release_db": ("texture.RELEASE_ANCHORS", (3.0, 8.5)),
    "raw_anisotropy": ("texture.PERCUSSIVE_ANCHORS", (0.385, 0.480)),
    "raw_eff_rank": ("harmony.VARIETY_ANCHORS", (6.5, 9.0)),
}


class Row:
    """Duck-types TrackAnalysis well enough for the axis value functions."""

    def __init__(self, d: dict) -> None:
        for k, v in d.items():
            try:
                setattr(self, k, float(v))
            except (TypeError, ValueError):
                setattr(self, k, v)


def load(path: Path) -> list[Row]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [Row(r) for r in csv.DictReader(fh)]


def percentiles(values: list[float], split: tuple[float, ...]) -> list[float]:
    return [float(np.percentile(values, p)) for p in split]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv", help="CSV exported by compas_cli --csv or the GUI")
    ap.add_argument("--split", type=float, nargs="+", default=[33.0, 67.0],
                    help="Percentile cut points (default: 33 67)")
    ap.add_argument("--per-rhythm", action="store_true",
                    help="Also print cuts computed within each rhythm")
    args = ap.parse_args()

    rows = load(Path(args.csv))
    if not rows:
        print("Empty CSV.", file=sys.stderr)
        return 1
    print(f"{len(rows)} tracks from {args.csv}")

    by_rhythm: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        by_rhythm[str(getattr(r, "rhythm", "?"))].append(r)
    print("  " + ", ".join(f"{k}: {len(v)}" for k, v in sorted(by_rhythm.items())))

    print(f"\n=== facet thresholds at percentiles {args.split} ===")
    print("Paste these into the matching Axis(...) in compas_core/facets.py.\n")
    for axis in AXES:
        vals = []
        for r in rows:
            try:
                v = axis.value(r)
            except Exception:  # noqa: BLE001 — a column may be missing
                v = None
            if v is not None and np.isfinite(v):
                vals.append(float(v))
        if len(vals) < 20:
            print(f"  {axis.key:<13} skipped — only {len(vals)} usable values")
            continue

        n_cuts = len(axis.thresholds)
        if n_cuts == 1:
            # Two-level axes are categorical (timing, mode, voice); a
            # percentile cut would be meaningless, so just report the split.
            share = float(np.mean(np.array(vals) >= axis.thresholds[0]))
            print(f"  {axis.key:<13} categorical — {share*100:5.1f}% above "
                  f"{axis.thresholds[0]:g} "
                  f"({axis.labels['english'][1]})")
            continue

        split = tuple(args.split[:n_cuts])
        cuts = percentiles(vals, split)
        current = ", ".join(f"{t:g}" for t in axis.thresholds)
        proposed = ", ".join(f"{c:.3g}" for c in cuts)
        shares = []
        edges = [-np.inf, *cuts, np.inf]
        for i in range(len(edges) - 1):
            shares.append(float(np.mean((np.array(vals) >= edges[i])
                                        & (np.array(vals) < edges[i + 1]))))
        print(f"  {axis.key:<13} thresholds=({proposed})"
              f"{'':<{max(0, 22-len(proposed))}}  was ({current})")
        print(f"  {'':<13}   range [{min(vals):.3g}, {max(vals):.3g}]  "
              f"median {np.median(vals):.3g}  "
              f"levels " + "/".join(f"{s*100:.0f}%" for s in shares))

    print("\n=== raw metric anchors ===")
    print("If a library uses only the middle of an anchor range, widen or "
          "narrow it\nso the 0-100 scores spread out again.\n")
    for field, (where, anchors) in RAW_ANCHORS.items():
        vals = [float(getattr(r, field)) for r in rows
                if isinstance(getattr(r, field, None), float)
                and np.isfinite(getattr(r, field))]
        if len(vals) < 20:
            print(f"  {field:<16} skipped — only {len(vals)} usable values")
            continue
        lo, hi = float(np.percentile(vals, 2)), float(np.percentile(vals, 98))
        used = (np.clip(np.array(vals), *anchors) - anchors[0]) / (
            anchors[1] - anchors[0])
        print(f"  {field:<16} p2-p98 [{lo:.4g}, {hi:.4g}]  "
              f"current {where} = {anchors}")
        print(f"  {'':<16}   suggested ({lo:.4g}, {hi:.4g})  "
              f"— scores now span {used.min()*100:.0f}-{used.max()*100:.0f} "
              f"of 0-100")

    if args.per_rhythm:
        print("\n=== per-rhythm medians ===")
        keys = [a.key for a in AXES if len(a.thresholds) > 1]
        print(f"  {'axis':<13}" + "".join(f"{k:>12}" for k in sorted(by_rhythm)))
        for axis in AXES:
            if axis.key not in keys:
                continue
            cells = []
            for rh in sorted(by_rhythm):
                vals = []
                for r in by_rhythm[rh]:
                    try:
                        v = axis.value(r)
                    except Exception:  # noqa: BLE001
                        v = None
                    if v is not None and np.isfinite(v):
                        vals.append(float(v))
                cells.append(f"{np.median(vals):12.3g}" if vals else f"{'—':>12}")
            print(f"  {axis.key:<13}" + "".join(cells))

    unknown = set(by_rhythm) - {r.value for r in Rhythm} - {"?"}
    if unknown:
        print(f"\n  note: unrecognised rhythm values in the CSV: {unknown}")
    if not RHYTHM_SPECS:  # pragma: no cover — sanity guard
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
