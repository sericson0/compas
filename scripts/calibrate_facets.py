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

from compas_core import harmony, texture  # noqa: E402
from compas_core.facets import AXES  # noqa: E402
from compas_core.rhythm import RHYTHM_SPECS, Rhythm  # noqa: E402

# Accented track names versus a cp1252 console — see validate_vocal.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Anchors map a raw measurement onto 0-100. Fitted on 19 tracks, they are
# the constants most likely to be wrong on a real library — too narrow and
# the score pins at 0 or 100 for a large slice of it, throwing away
# resolution exactly where the facet cuts need it.
#
# These are the anchors this script may propose changing. Drive and energy
# have anchors too, but those are validated against published orchestra
# separations, so they are only reported, never re-fitted here.
RAW_ANCHORS = {
    "raw_attack_db": ("texture.ATTACK_ANCHORS", texture.ATTACK_ANCHORS),
    "raw_release_db": ("texture.RELEASE_ANCHORS", texture.RELEASE_ANCHORS),
    "raw_anisotropy": ("texture.PERCUSSIVE_ANCHORS",
                       texture.PERCUSSIVE_ANCHORS),
    "raw_eff_rank": ("harmony.VARIETY_ANCHORS", harmony.VARIETY_ANCHORS),
}

# How each 0-100 score is rebuilt from raw columns, so thresholds can be
# fitted on the RE-ANCHORED scale. Proposing anchors and thresholds
# independently is a trap: apply both and the thresholds no longer mean what
# was fitted, because the scale underneath them moved.
DERIVED = {
    "articulation": ((("raw_attack_db", 0.5), ("raw_release_db", 0.5))),
    "texture": ((("raw_anisotropy", 1.0),)),
    "harmony": ((("raw_eff_rank", 1.0),)),
}

# 0-100 columns to report clipping for, including the ones we never re-fit.
SCORE_COLUMNS = ("drive", "syncopation", "articulation", "percussiveness",
                 "harmonic_variety")


def _norm(value: float, anchor: tuple[float, float]) -> float:
    lo, hi = anchor
    return float(np.clip((value - lo) / max(hi - lo, 1e-12), 0.0, 1.0))


def rescored(rows: list["Row"], axis_key: str,
             anchors: dict[str, tuple[float, float]]) -> list[float] | None:
    """The axis's 0-100 score recomputed under proposed anchors."""
    recipe = DERIVED.get(axis_key)
    if recipe is None:
        return None
    out = []
    for r in rows:
        total = 0.0
        ok = True
        for field, weight in recipe:
            raw = getattr(r, field, None)
            if not isinstance(raw, float) or not np.isfinite(raw):
                ok = False
                break
            total += weight * _norm(raw, anchors[field])
        if ok:
            out.append(100.0 * total)
    return out


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
    ap.add_argument("--anchor-pct", type=float, nargs=2, default=[1.0, 99.0],
                    metavar=("LO", "HI"),
                    help="Percentiles for proposed anchors (default: 1 99)")
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

    # --- step 1: anchors, because the thresholds depend on them -----------
    print("\n=== step 1: raw metric anchors ===")
    print("A score pinned at 0 or 100 carries no information. Apply these "
          "FIRST —\nthe thresholds in step 2 are fitted to the scale they "
          "produce.\n")
    anchor_map: dict[str, tuple[float, float]] = {}
    for field, (where, current) in RAW_ANCHORS.items():
        vals = [float(getattr(r, field)) for r in rows
                if isinstance(getattr(r, field, None), float)
                and np.isfinite(getattr(r, field))]
        if len(vals) < 20:
            anchor_map[field] = current
            print(f"  {field:<16} skipped — only {len(vals)} usable values")
            continue
        arr = np.array(vals)
        lo = float(np.percentile(arr, args.anchor_pct[0]))
        hi = float(np.percentile(arr, args.anchor_pct[1]))
        at_lo = float(np.mean(arr <= current[0])) * 100
        at_hi = float(np.mean(arr >= current[1])) * 100
        anchor_map[field] = (lo, hi)
        print(f"  {where} = ({lo:.4g}, {hi:.4g})")
        print(f"  {'':<16}   was ({current[0]:g}, {current[1]:g}) — "
              f"clipped {at_lo:.1f}% at 0 and {at_hi:.1f}% at 100")

    print("\n  clipping in the shipped scores (for reference; drive and "
          "energy anchors\n  are validated elsewhere and are not re-fitted "
          "here):")
    for col in SCORE_COLUMNS:
        vals = [float(getattr(r, col)) for r in rows
                if isinstance(getattr(r, col, None), float)]
        if len(vals) < 20:
            continue
        arr = np.array(vals)
        print(f"    {col:<18} {np.mean(arr <= 0)*100:5.1f}% at 0   "
              f"{np.mean(arr >= 100)*100:5.1f}% at 100")

    print(f"\n=== step 2: facet thresholds at percentiles {args.split} ===")
    print("Fitted on the re-anchored scale above. Paste into the matching "
          "Axis(...)\nin compas_core/facets.py.\n")
    for axis in AXES:
        vals = rescored(rows, axis.key, anchor_map)
        if vals is None:
            vals = []
            for r in rows:
                try:
                    v = axis.value(r)
                except Exception:  # noqa: BLE001 — a column may be missing
                    v = None
                if v is not None and np.isfinite(v):
                    vals.append(float(v))
        elif len(vals) >= 20:
            print(f"  {'':<13} (recomputed under the proposed anchors)")
        if len(vals) < 20:
            print(f"  {axis.key:<13} skipped — only {len(vals)} usable values")
            continue

        n_cuts = len(axis.thresholds)
        if axis.categorical:
            # Named classes, not a continuum. Percentile-fitting Voice's
            # 0/1/2 would propose thresholds of (0, 2) and reclassify every
            # instrumental as a refrain. Report the mix instead.
            arr = np.array(vals)
            names = axis.labels["english"]
            shares = []
            edges = [-np.inf, *axis.thresholds, np.inf]
            for i in range(len(edges) - 1):
                share = float(np.mean((arr >= edges[i]) & (arr < edges[i + 1])))
                shares.append(f"{names[i]} {share*100:.0f}%")
            print(f"  {axis.key:<13} categorical — " + ", ".join(shares))
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

    if args.per_rhythm:
        print("\n=== per-rhythm medians ===")
        keys = [a.key for a in AXES if not a.categorical]
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
