"""Rhythmic drive, dynamic range, and the composite energy score.

Raw feature -> normalized 0..1 via calibration anchors -> weighted composite
mapped to the DJ-facing 1-10 energy scale. Anchors are calibrated against the
golden-age example set (see scripts/validate_examples.py); adjust there, not
in the formulas.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from compas_core.rhythm import RhythmSpec
from compas_core.tempo import HOP, TempoResult


@dataclass
class EnergyResult:
    energy: float          # 1-10 composite
    drive: float           # 0-100 how hard the compás is marked
    dynamic_range_db: float
    onset_density: float   # onsets per second
    # Raw components (kept for calibration/debugging)
    raw_beat_contrast: float
    raw_percussive_ratio: float
    raw_loudness_var: float


# Calibration anchors: raw values mapped to 0 and 1 for each component.
# Set from the observed distributions across the golden-age example corpus
# (see scratch CSV raws): beat contrast ran 1.9 (Temo) to 5.3 (Biagi),
# percussive ratio 0.27-0.53, onset density 1.8 (late Pugliese) to 5.0
# (milongas), loudness std 2.9-6.6 dB (Pugliese top).
_ANCHORS = {
    "drive_beat_contrast": (1.9, 3.8),   # mean oenv at beats / overall mean
    "percussive_ratio": (0.26, 0.52),    # percussive RMS share after HPSS
    "onset_density": (1.8, 5.0),         # onsets / second
    "tempo_rel": (0.95, 1.15),           # bpm / genre-typical bpm
    "loudness_var": (2.8, 6.0),          # std of short-term RMS dB
}

_WEIGHTS = {"drive": 0.50, "tempo": 0.20, "onsets": 0.15, "loudvar": 0.15}


def _norm(value: float, anchor: tuple[float, float]) -> float:
    lo, hi = anchor
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def analyze_energy(
    y: np.ndarray,
    y_percussive: np.ndarray,
    sr: int,
    tempo: TempoResult,
    spec: RhythmSpec,
) -> EnergyResult:
    import librosa

    oenv = tempo.onset_env

    # --- rhythmic drive: onset energy concentrated at beat positions -------
    beat_frames = librosa.time_to_frames(tempo.beat_times, sr=sr, hop_length=HOP)
    beat_frames = beat_frames[(beat_frames >= 0) & (beat_frames < len(oenv))]
    mean_env = float(oenv.mean()) or 1e-9
    beat_contrast = float(oenv[beat_frames].mean()) / mean_env if len(beat_frames) else 1.0

    rms_total = float(np.sqrt(np.mean(y**2))) or 1e-9
    rms_perc = float(np.sqrt(np.mean(y_percussive**2)))
    percussive_ratio = rms_perc / rms_total

    # Beat contrast carries most of the weight: the percussive ratio is
    # noisier on shellac transfers (surface noise reads as percussive).
    drive01 = 0.7 * _norm(beat_contrast, _ANCHORS["drive_beat_contrast"]) \
            + 0.3 * _norm(percussive_ratio, _ANCHORS["percussive_ratio"])
    drive = round(drive01 * 100, 0)

    # --- onset density ------------------------------------------------------
    onsets = librosa.onset.onset_detect(onset_envelope=oenv, sr=sr, hop_length=HOP)
    duration = len(y) / sr
    onset_density = len(onsets) / max(duration, 1e-9)

    # --- dynamic range: spread of short-term loudness -----------------------
    frame = sr // 2  # 500 ms windows, 250 ms hop
    rms = librosa.feature.rms(y=y, frame_length=frame, hop_length=frame // 2)[0]
    rms_db = 20 * np.log10(np.clip(rms, 1e-6, None))
    active = rms_db[rms_db > rms_db.max() - 40]  # ignore lead-in/out silence
    dynamic_range_db = float(np.percentile(active, 95) - np.percentile(active, 10))
    loudness_var = float(np.std(active))

    # --- composite energy ----------------------------------------------------
    tempo_rel = tempo.bpm / spec.bpm_typical
    e01 = (
        _WEIGHTS["drive"] * drive01
        + _WEIGHTS["tempo"] * _norm(tempo_rel, _ANCHORS["tempo_rel"])
        + _WEIGHTS["onsets"] * _norm(onset_density, _ANCHORS["onset_density"])
        + _WEIGHTS["loudvar"] * _norm(loudness_var, _ANCHORS["loudness_var"])
    )
    energy = round(1 + e01 * 9, 1)

    return EnergyResult(
        energy=energy,
        drive=drive,
        dynamic_range_db=round(dynamic_range_db, 1),
        onset_density=round(onset_density, 2),
        raw_beat_contrast=round(beat_contrast, 3),
        raw_percussive_ratio=round(percussive_ratio, 3),
        raw_loudness_var=round(loudness_var, 3),
    )
