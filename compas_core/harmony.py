"""Harmonic complexity: how much distinct harmony a piece actually uses.

Read this one with more scepticism than the rest of COMPAS. Chroma on
shellac-era mono is smeared -- surface noise puts energy in every pitch
class -- and the first three things tried here did not survive contact with
the example corpus:

  * whole-song chroma entropy is pinned at 0.98 for every track, because
    the noise floor dominates the average;
  * harmonic-change rate per *second* (Harte's HCDF) just re-sorts the
    corpus by genre: valses change chords more often per second because
    they are faster, which says nothing about complexity;
  * the same rate per *bar* inverts that and sorts by genre the other way.

What is reported instead:

**Variety** (the headline, 0-100). Beat-synchronous CENS chroma, each pitch
class's own 20th percentile subtracted (hiss lifts all twelve by roughly
the same amount, so the floor is removable), columns L2-normalised, matrix
mean-removed, then the effective rank of the result -- exp of the entropy
of its normalised singular values. Read it as "how many independent
harmonic shapes does this piece use". Biagi's *El Incendio*, four chords
hammered for three minutes, comes last at 6.7; the corpus tops out at 8.8.

**Change** (raw, for calibration). Mean cosine distance between
consecutive *beat-synchronous* chroma frames, i.e. chord change per beat.
Per beat rather than per second is what removes the tempo confound above.

Validation status: on a 19-track corpus, variety agrees with a hand-written
expert ordering at Spearman 0.41. That is suggestive, not established --
the ordering is one person's judgement and the corpus is tiny. Treat this
metric as provisional until it has been run over a real library
(``scripts/calibrate_facets.py``), which is why the "harmony" facet axis is
off by default.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

FLOOR_PERCENTILE = 20.0
MIN_BEATS = 16

# Corpus spread of effective rank was 6.71-8.82.
VARIETY_ANCHORS = (6.5, 9.0)


@dataclass
class HarmonyResult:
    harmonic_variety: float    # 0-100, how many distinct harmonies
    raw_eff_rank: float        # effective rank of the beat-chroma matrix
    raw_chord_change: float    # mean cosine distance per beat


def _beat_sync(chroma: np.ndarray, beat_times: np.ndarray, sr: int,
               hop: int) -> np.ndarray | None:
    import librosa

    frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=hop)
    frames = frames[(frames >= 0) & (frames < chroma.shape[1])]
    if len(frames) < MIN_BEATS:
        return None
    return librosa.util.sync(chroma, frames, aggregate=np.mean)


def _unit_columns(X: np.ndarray) -> np.ndarray:
    return X / np.clip(np.linalg.norm(X, axis=0, keepdims=True), 1e-9, None)


def analyze_harmony(
    chroma_cens: np.ndarray,
    chroma_cqt: np.ndarray,
    beat_times: np.ndarray,
    sr: int,
    hop: int = 512,
) -> HarmonyResult:
    cens = _beat_sync(chroma_cens, beat_times, sr, hop)
    cqt = _beat_sync(chroma_cqt, beat_times, sr, hop)
    if cens is None or cqt is None or cens.shape[1] < 3:
        return HarmonyResult(0.0, 0.0, 0.0)

    floor = np.percentile(cens, FLOOR_PERCENTILE, axis=1, keepdims=True)
    X = _unit_columns(np.clip(cens - floor, 0.0, None))
    X = X - X.mean(axis=1, keepdims=True)
    ev = np.linalg.svd(X, compute_uv=False) ** 2
    p = ev / max(ev.sum(), 1e-12)
    eff_rank = float(np.exp(-(p * np.log(np.clip(p, 1e-12, None))).sum()))

    U = _unit_columns(cqt)
    cos = np.sum(U[:, :-1] * U[:, 1:], axis=0)
    change = float(np.mean(1.0 - np.clip(cos, -1.0, 1.0)))

    lo, hi = VARIETY_ANCHORS
    variety = 100.0 * float(np.clip((eff_rank - lo) / (hi - lo), 0.0, 1.0))
    return HarmonyResult(
        harmonic_variety=round(variety, 0),
        raw_eff_rank=round(eff_rank, 3),
        raw_chord_change=round(change, 4),
    )
