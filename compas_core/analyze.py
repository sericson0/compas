"""Top-level analysis orchestration: one call per track.

``analyze_file(path)`` -> :class:`TrackAnalysis` with every metric the GUI,
CLI, and tag writer need.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

from compas_core.audio import load_audio
from compas_core.energy import analyze_energy
from compas_core.key import analyze_key
from compas_core.rhythm import (
    RHYTHM_SPECS,
    Rhythm,
    fold_bpm_into_range,
    rhythm_from_genre,
)
from compas_core.tags import FileTags, read_tags
from compas_core.tempo import HOP, analyze_tempo


@dataclass
class TrackAnalysis:
    path: str
    filename: str
    title: str | None
    artist: str | None
    date: str | None
    duration_sec: float

    rhythm: str                # tango / vals / milonga
    rhythm_source: str         # override / genre-tag / audio / default
    time_signature: str        # 4/4, 3/4, 2/4

    bpm: float                 # median beat-level BPM
    bpm_low: float
    bpm_high: float
    bars_per_min: float
    stability: float           # 0-100
    tempo_cv: float            # raw local-tempo variation (calibration aid)
    timing: str                # fixed / flexible

    key: str
    camelot: str
    key_confidence: float
    tag_bpm: str | None        # pre-existing BPM tag (MIK/Serato/…), if any
    tag_key: str | None        # pre-existing initial-key tag, if any

    energy: float              # 1-10
    drive: float               # 0-100
    dynamic_range_db: float
    onset_density: float
    raw_beat_contrast: float   # calibration aids
    raw_percussive_ratio: float
    raw_loudness_var: float

    def to_dict(self) -> dict:
        return asdict(self)

    def tag_fields(self, *, key_as_camelot: bool = False) -> dict[str, str]:
        """Canonical tag fields for compas_core.tags.write_tags."""
        return {
            "BPM": f"{self.bpm:.1f}",
            "INITIALKEY": self.camelot if key_as_camelot else self.key,
            "COMPAS_RHYTHM": self.rhythm,
            "COMPAS_ENERGY": f"{self.energy:.1f}",
            "COMPAS_DRIVE": f"{self.drive:.0f}",
            "COMPAS_STABILITY": f"{self.stability:.0f}",
            "COMPAS_TIMING": self.timing,
            "COMPAS_BPM_RANGE": f"{self.bpm_low:.0f}-{self.bpm_high:.0f}",
            "COMPAS_BARS_PER_MIN": f"{self.bars_per_min:.1f}",
            "COMPAS_DYNAMIC_RANGE_DB": f"{self.dynamic_range_db:.1f}",
        }


def _detect_rhythm_from_audio(oenv: np.ndarray, sr: int) -> Rhythm:
    """Meter/tempo heuristic when no usable GENRE tag exists.

    Triple vs duple meter from the autocorrelation of beat-level accents;
    duple is then split tango vs milonga by which genre's tempo range the
    (folded) tactus fits with less distortion.
    """
    import librosa

    tempo_free = float(
        librosa.feature.tempo(onset_envelope=oenv, sr=sr, hop_length=HOP,
                              start_bpm=120.0, std_bpm=1.5, max_tempo=320.0)[0]
    )
    _, beats = librosa.beat.beat_track(
        onset_envelope=oenv, sr=sr, hop_length=HOP,
        bpm=tempo_free, tightness=80, units="frames",
    )
    if len(beats) >= 16:
        accents = oenv[beats].astype(float)
        accents -= accents.mean()
        denom = float(np.sum(accents**2)) or 1e-9

        def acf(lag: int) -> float:
            return float(np.sum(accents[:-lag] * accents[lag:])) / denom

        # Strong 3-beat accent periodicity that beats 2- and 4-beat -> vals
        if acf(3) > max(acf(2), acf(4)) + 0.03:
            return Rhythm.VALS

    # Duple: pick tango vs milonga by tempo-range fit
    import math
    costs = {}
    for r in (Rhythm.TANGO, Rhythm.MILONGA):
        spec = RHYTHM_SPECS[r]
        folded = fold_bpm_into_range(tempo_free, spec)
        cost = abs(math.log(folded / spec.bpm_typical))
        if not (spec.bpm_min <= folded <= spec.bpm_max):
            cost += 10
        costs[r] = cost
    return min(costs, key=costs.get)


def resolve_rhythm(
    tags: FileTags,
    oenv: np.ndarray | None,
    sr: int,
    override: str | Rhythm | None = None,
) -> tuple[Rhythm, str]:
    """Resolution order: explicit override > GENRE tag > audio heuristic."""
    if override and str(override) != "auto":
        return Rhythm(str(override)), "override"
    tagged = rhythm_from_genre(tags.genre)
    if tagged is not None:
        return tagged, "genre-tag"
    if oenv is not None:
        return _detect_rhythm_from_audio(oenv, sr), "audio"
    return Rhythm.TANGO, "default"


def analyze_file(
    path: str | Path,
    rhythm: str | Rhythm | None = None,
) -> TrackAnalysis:
    """Analyze one audio file. ``rhythm``: tango/vals/milonga/auto/None."""
    import librosa

    path = Path(path)
    tags = read_tags(path)
    y, sr = load_audio(path)
    duration = len(y) / sr

    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    resolved, source = resolve_rhythm(tags, oenv, sr, override=rhythm)
    spec = RHYTHM_SPECS[resolved]

    tempo = analyze_tempo(y, sr, spec, onset_env=oenv)

    y_harm, y_perc = librosa.effects.hpss(y)
    key = analyze_key(y_harm, sr)
    energy = analyze_energy(y, y_perc, sr, tempo, spec)

    return TrackAnalysis(
        path=str(path),
        filename=path.name,
        title=tags.title,
        artist=tags.artist,
        date=tags.date,
        duration_sec=round(duration, 1),
        rhythm=resolved.value,
        rhythm_source=source,
        time_signature=f"{spec.beats_per_bar}/4",
        bpm=tempo.bpm,
        bpm_low=tempo.bpm_low,
        bpm_high=tempo.bpm_high,
        bars_per_min=round(tempo.bpm / spec.beats_per_bar, 1),
        stability=tempo.stability,
        tempo_cv=tempo.tempo_cv,
        timing="fixed" if tempo.is_fixed_time else "flexible",
        key=key.key,
        camelot=key.camelot,
        key_confidence=key.confidence,
        tag_bpm=tags.existing_bpm,
        tag_key=tags.existing_key,
        energy=energy.energy,
        drive=energy.drive,
        dynamic_range_db=energy.dynamic_range_db,
        onset_density=energy.onset_density,
        raw_beat_contrast=energy.raw_beat_contrast,
        raw_percussive_ratio=energy.raw_percussive_ratio,
        raw_loudness_var=energy.raw_loudness_var,
    )
