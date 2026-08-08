"""Rhythm (song type) definitions and resolution.

The three social-tango rhythms differ in meter and in plausible tempo range.
The tempo ranges are the key defense against octave errors in beat tracking:
a vals reported at 60 BPM and a tango reported at 240 BPM are both octave
mistakes, and folding the tracker's estimate into the genre range fixes them.

Tempo ranges are expressed at the *beat* (tactus) level — the pulse a dancer
steps to — for golden-age recordings:

- tango   4/4: ~100-145 BPM beat level (D'Arienzo fast ~132, Di Sarli ~118)
- vals    3/4: ~150-215 BPM quarter-note level (bars: 50-72 per minute)
- milonga 2/4: ~85-135 BPM (habanera pulse)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Rhythm(str, Enum):
    TANGO = "tango"
    VALS = "vals"
    MILONGA = "milonga"

    def __str__(self) -> str:  # pragma: no cover
        return self.value


@dataclass(frozen=True)
class RhythmSpec:
    rhythm: Rhythm
    beats_per_bar: int      # per the user-facing convention: 4/4, 3/4, 2/4
    bpm_min: float          # plausible beat-level tempo range
    bpm_max: float
    bpm_typical: float      # center of the golden-age distribution
    # Tempo tracking happens at the level where the periodicity is sharpest:
    # tango/milonga at the beat; vals at the bar (the uneven oom-pah-pah
    # smears the beat-level autocorrelation, the bar period stays clean).
    track_unit_beats: int = 1
    # Harmonic reinforcement multiples (relative to the tracked lag) and
    # weights: a true tempo also shows periodicity at these lag multiples.
    harmonics: tuple[tuple[int, float], ...] = ((1, 1.0),)
    # Stability score at/above which timing counts as "fixed". Vals gets a
    # lower bar: section-level tempo elasticity is idiomatic there and does
    # not threaten danceability the way tango rubato does.
    fixed_threshold: float = 70.0


RHYTHM_SPECS: dict[Rhythm, RhythmSpec] = {
    Rhythm.TANGO: RhythmSpec(Rhythm.TANGO, beats_per_bar=4,
                             bpm_min=100.0, bpm_max=145.0, bpm_typical=122.0,
                             track_unit_beats=1,
                             harmonics=((1, 1.0), (2, 0.6), (4, 0.3))),
    Rhythm.VALS: RhythmSpec(Rhythm.VALS, beats_per_bar=3,
                            bpm_min=150.0, bpm_max=215.0, bpm_typical=178.0,
                            track_unit_beats=3,
                            harmonics=((1, 1.0), (2, 0.5)),
                            fixed_threshold=50.0),
    Rhythm.MILONGA: RhythmSpec(Rhythm.MILONGA, beats_per_bar=2,
                               bpm_min=85.0, bpm_max=135.0, bpm_typical=104.0,
                               track_unit_beats=1,
                               harmonics=((1, 1.0), (2, 0.6))),
}

# Substrings (lowercased) mapped to rhythms for GENRE-tag auto-detection.
_GENRE_MAP = [
    ("milonga", Rhythm.MILONGA),
    ("candombe", Rhythm.MILONGA),
    ("vals", Rhythm.VALS),
    ("waltz", Rhythm.VALS),
    ("tango", Rhythm.TANGO),
]


def rhythm_from_genre(genre: str | None) -> Rhythm | None:
    """Map a GENRE tag value to a rhythm, or None if unrecognized."""
    if not genre:
        return None
    g = genre.lower()
    for needle, rhythm in _GENRE_MAP:
        if needle in g:
            return rhythm
    return None


def fold_bpm_into_range(bpm: float, spec: RhythmSpec) -> float:
    """Fold a tempo estimate into the rhythm's plausible range.

    Beat trackers routinely report half, double, third, or triple the
    danceable tempo (e.g. a vals bar rate of 59 instead of the quarter-note
    pulse at 177). Try small integer ratios and pick the candidate closest
    (in log-tempo) to the genre's typical tempo, preferring in-range values.
    """
    import math

    factors = (1.0, 2.0, 3.0, 4.0, 0.5, 1 / 3, 0.25, 1.5, 2 / 3)
    best, best_cost = bpm, float("inf")
    for f in factors:
        cand = bpm * f
        cost = abs(math.log(cand / spec.bpm_typical))
        if not (spec.bpm_min <= cand <= spec.bpm_max):
            cost += 10.0  # out-of-range candidates only win if nothing fits
        if cost < best_cost:
            best, best_cost = cand, cost
    return best
