"""Rhythmic drive, syncopation, dynamics, and the composite energy score.

Drive
-----
Drive measures how hard the compas is marked. It is computed as the ratio
of spectral flux *on* the beat to spectral flux exactly *between* beats, in
frequency bands chosen for shellac-era material:

    low  150-400 Hz   contrabass and piano left hand marking the compas
    mid  400-1200 Hz  bandoneon body

Two earlier definitions were tried and rejected against the example corpus:

  * on-beat flux divided by the track's *own mean* is tempo-confounded. At
    vals tempos the attacks are dense enough to raise that mean, which
    compressed the ratio and made valses read as undriven (class means were
    tango 54 / vals 24 / milonga 30 on a metric where vals is in fact the
    most crisply marked music in the corpus).
  * full-band flux washes the distinction out entirely; the bass band is
    where marcato actually lives.

The on-beat/off-beat form fixes the tempo confound (class means become
roughly tango 3.4 / vals 3.6 / milonga 2.1 on the raw ratio) and separates
orchestras from themselves -- D'Arienzo's rhythmic El Flete scores 7.1
against his own lyrical Amarras at 1.2.

Syncopation
-----------
The reciprocal view: off-beat flux over on-beat flux, broadband. Milonga's
habanera puts real weight between the beats, so it scores high; Biagi's
straight marking scores low. Only weakly correlated with drive
(r = -0.32 across the corpus), so it carries independent information.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from compas_core.rhythm import RhythmSpec
from compas_core.tempo import HOP, TempoResult

N_FFT = 2048

# Analysis bands (Hz). Shellac rolls off below ~150 Hz and above ~5 kHz, so
# the usual 20 Hz / 7-22 kHz bands used for modern material are empty here.
BAND_LOW = (150.0, 400.0)
BAND_MID = (400.0, 1200.0)

# Drive: combine the two bands in the log domain, weighted toward the bass,
# then map to 0-100 between these log-ratio anchors. Anchors set from the
# corpus spread (log-combined values ran about -0.02 to 2.08).
DRIVE_BAND_WEIGHTS = (0.7, 0.3)   # (low, mid)
DRIVE_LOG_ANCHORS = (-0.15, 2.10)

_ANCHORS = {
    "onset_density": (1.8, 5.0),         # onsets / second
    "tempo_rel": (0.95, 1.15),           # bpm / genre-typical bpm
    "loudness_var": (2.8, 6.0),          # std of short-term RMS dB
}

# The rhythmic half of energy credits marcato AND syncopation. Drive alone
# was too narrow: it rewards hard on-beat marking, which is how a tango
# orchestra generates drive but NOT how a milonga does. The habanera puts
# its weight between the beats, so milongas score low on drive by
# construction, and a drive-only composite rated them around 3.7/10 --
# obviously wrong for the liveliest music in the repertoire.
_RHYTHM_MIX = {"drive": 0.75, "syncopation": 0.25}
_WEIGHTS = {"rhythm": 0.50, "tempo": 0.15, "onsets": 0.20, "loudvar": 0.15}


@dataclass
class EnergyResult:
    energy: float          # 1-10 composite
    drive: float           # 0-100, how hard the compas is marked
    syncopation: float     # 0-100, how much weight falls between beats
    dynamic_range_db: float
    onset_density: float   # onsets per second
    # Raw components, kept for calibration and debugging
    raw_drive_low: float   # on/off-beat flux ratio, 150-400 Hz
    raw_drive_mid: float   # on/off-beat flux ratio, 400-1200 Hz
    raw_syncopation: float  # off/on-beat ratio, broadband
    raw_loudness_var: float


def _norm(value: float, anchor: tuple[float, float]) -> float:
    lo, hi = anchor
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def _beat_offbeat_frames(beat_times: np.ndarray, sr: int, n_frames: int):
    """Frame indices for beat positions and for the midpoints between them."""
    import librosa

    off_times = (beat_times[:-1] + beat_times[1:]) / 2
    bf = librosa.time_to_frames(beat_times, sr=sr, hop_length=HOP)
    of = librosa.time_to_frames(off_times, sr=sr, hop_length=HOP)
    bf = bf[(bf >= 0) & (bf < n_frames)]
    of = of[(of >= 0) & (of < n_frames)]
    return bf, of


def _flux_contrast(S: np.ndarray, freqs: np.ndarray, band: tuple[float, float],
                   bf: np.ndarray, of: np.ndarray) -> float:
    """On-beat / off-beat positive spectral flux within a frequency band.

    Flux rather than level: a legato orchestra can be loud on the beat
    without articulating it, and only the attack should count as drive.
    """
    rows = np.where((freqs >= band[0]) & (freqs < band[1]))[0]
    if len(rows) == 0 or len(bf) == 0 or len(of) == 0:
        return 1.0
    env = S[rows, :].sum(axis=0)
    flux = np.maximum(0.0, np.diff(env, prepend=env[0]))
    on = float(flux[bf].mean())
    off = float(flux[of].mean())
    return on / max(off, 1e-9)


def analyze_energy(
    y: np.ndarray,
    sr: int,
    tempo: TempoResult,
    spec: RhythmSpec,
    S: np.ndarray | None = None,
    onsets: np.ndarray | None = None,
) -> EnergyResult:
    """``S`` (magnitude STFT at N_FFT/HOP) and ``onsets`` (frame indices) are
    shared with the texture metrics; pass them in to avoid recomputing."""
    import librosa

    oenv = tempo.onset_env

    # --- drive: band-limited on/off-beat flux contrast ---------------------
    if S is None:
        S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    bf, of = _beat_offbeat_frames(tempo.beat_times, sr, S.shape[1])

    if len(tempo.beat_times) >= 8 and len(bf) and len(of):
        drive_low = _flux_contrast(S, freqs, BAND_LOW, bf, of)
        drive_mid = _flux_contrast(S, freqs, BAND_MID, bf, of)
        wl, wm = DRIVE_BAND_WEIGHTS
        log_drive = wl * np.log(max(drive_low, 1e-3)) + wm * np.log(max(drive_mid, 1e-3))
        drive01 = _norm(float(log_drive), DRIVE_LOG_ANCHORS)
    else:
        drive_low = drive_mid = 1.0
        drive01 = 0.0
    drive = round(drive01 * 100, 0)

    # --- syncopation: the reciprocal view, broadband -----------------------
    if len(bf) and len(of):
        raw_sync = float(oenv[of].mean() / max(oenv[bf].mean(), 1e-9))
    else:
        raw_sync = 0.0
    # 0..1 maps to a 0-100 display; ratios above 1 (more off- than on-beat
    # energy) are possible but rare, so clamp.
    syncopation = round(float(np.clip(raw_sync, 0.0, 1.0)) * 100, 0)

    # --- onset density ------------------------------------------------------
    if onsets is None:
        onsets = librosa.onset.onset_detect(
            onset_envelope=oenv, sr=sr, hop_length=HOP)
    duration = len(y) / sr
    onset_density = len(onsets) / max(duration, 1e-9)

    # --- dynamics (legacy RMS spread; LRA in loudness.py is the better one) -
    frame = sr // 2  # 500 ms windows, 250 ms hop
    rms = librosa.feature.rms(y=y, frame_length=frame, hop_length=frame // 2)[0]
    rms_db = 20 * np.log10(np.clip(rms, 1e-6, None))
    active = rms_db[rms_db > rms_db.max() - 40]  # ignore lead-in/out silence
    dynamic_range_db = float(np.percentile(active, 95) - np.percentile(active, 10))
    loudness_var = float(np.std(active))

    # --- composite energy ----------------------------------------------------
    rhythm01 = (_RHYTHM_MIX["drive"] * drive01
                + _RHYTHM_MIX["syncopation"] * float(np.clip(raw_sync, 0.0, 1.0)))
    tempo_rel = tempo.bpm / spec.bpm_typical
    e01 = (
        _WEIGHTS["rhythm"] * rhythm01
        + _WEIGHTS["tempo"] * _norm(tempo_rel, _ANCHORS["tempo_rel"])
        + _WEIGHTS["onsets"] * _norm(onset_density, _ANCHORS["onset_density"])
        + _WEIGHTS["loudvar"] * _norm(loudness_var, _ANCHORS["loudness_var"])
    )
    energy = round(1 + e01 * 9, 1)

    return EnergyResult(
        energy=energy,
        drive=drive,
        syncopation=syncopation,
        dynamic_range_db=round(dynamic_range_db, 1),
        onset_density=round(onset_density, 2),
        raw_drive_low=round(drive_low, 3),
        raw_drive_mid=round(drive_mid, 3),
        raw_syncopation=round(raw_sync, 3),
        raw_loudness_var=round(loudness_var, 3),
    )
