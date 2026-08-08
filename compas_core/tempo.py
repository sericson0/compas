"""Tempo, beat tracking, and tempo-stability (rubato) analysis.

Strategy
--------
1. Onset-strength envelope at a fine hop (256) -> autocorrelation tempogram
   (~6 s windows), rows restricted to the rhythm's plausible beat-tempo
   range (kills octave errors at the source).
2. Columns are block-averaged to ~5 Hz (rubato is a phrase-level
   phenomenon) and decoded with **Viterbi smoothing**: a transition penalty
   on log-tempo jumps makes metrical-level flipping (e.g. the 4/3 habanera
   harmonic in milongas) expensive while gradual rubato stays cheap.
3. The decoded path is refined with parabolic interpolation in lag domain
   for sub-bin precision (crucial for vals, where bins are ~4% apart).
4. From the local tempo curve:
   - bpm: median (the single number a DJ files the song under)
   - bpm_low/high: 10th/90th percentile (the honest range)
   - stability 0-100 from the curve's coefficient of variation
5. Beat times from a conventional tracker seeded at the median tempo —
   used downstream for the rhythmic-drive metric.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from compas_core.rhythm import RhythmSpec

HOP = 512          # analysis hop for onset/drive features (shared)
TEMPO_HOP = 256    # finer hop for the tempogram (lag resolution at high BPM)

TEMPOGRAM_WINDOW_SEC = 6.0
BLOCK_SEC = 0.20       # tempo curve time step after block averaging
SMOOTH_SEC = 2.0

PRIOR_SIGMA_OCT = 0.5  # log2 std of the soft prior toward the typical tempo
TRANSITION_LAMBDA = 60.0  # Viterbi penalty on (log tempo jump)^2 per step

# Stability mapping: score = 100 / (1 + (CV / CV_HALF)**2)
# CV_HALF is the local-tempo coefficient of variation that scores 50.
# The fixed/flexible threshold lives on RhythmSpec (vals is more lenient).
CV_HALF = 0.055


@dataclass
class TempoResult:
    bpm: float                 # median local BPM (the headline number)
    bpm_low: float             # 10th percentile of local tempo
    bpm_high: float            # 90th percentile
    stability: float           # 0-100, higher = steadier
    tempo_cv: float            # raw coefficient of variation (for calibration)
    is_fixed_time: bool
    beat_times: np.ndarray     # seconds
    onset_env: np.ndarray      # hop=HOP envelope for downstream metrics
    local_bpm: np.ndarray      # smoothed BPM curve (BLOCK_SEC steps)


def _viterbi_tempo_path(scores: np.ndarray, bpms: np.ndarray) -> np.ndarray:
    """Max-sum decode of tempo-bin path with a log-tempo transition penalty.

    scores: (n_bins, n_blocks) non-negative salience; bpms: (n_bins,).
    Returns bin index per block.
    """
    log_obs = np.log(scores + 1e-9)
    logt = np.log(bpms)
    trans = -TRANSITION_LAMBDA * (logt[:, None] - logt[None, :]) ** 2

    n_bins, n_blocks = scores.shape
    dp = log_obs[:, 0].copy()
    back = np.zeros((n_blocks, n_bins), dtype=np.int32)
    for t in range(1, n_blocks):
        step = dp[None, :] + trans  # step[j, i]: arriving at j from i
        back[t] = np.argmax(step, axis=1)
        dp = step[np.arange(n_bins), back[t]] + log_obs[:, t]
    path = np.zeros(n_blocks, dtype=np.int32)
    path[-1] = int(np.argmax(dp))
    for t in range(n_blocks - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path


def _local_tempo_curve(y: np.ndarray, sr: int, spec: RhythmSpec) -> np.ndarray:
    """Local beat-level tempo (one value per BLOCK_SEC), range-constrained."""
    import librosa
    import scipy.signal

    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=TEMPO_HOP)
    frame_rate = sr / TEMPO_HOP
    win = int(TEMPOGRAM_WINDOW_SEC * frame_rate) | 1
    tg = librosa.feature.tempogram(
        onset_envelope=oenv, sr=sr, hop_length=TEMPO_HOP, win_length=win
    )  # (win, n_frames); row index == lag in frames

    lags = np.arange(tg.shape[0], dtype=float)
    with np.errstate(divide="ignore"):
        bpms_all = 60.0 * frame_rate / lags

    # Track at the rhythm's sharpest metrical level (beat for tango/milonga,
    # bar for vals); convert back to beat BPM at the end.
    unit = spec.track_unit_beats
    unit_min, unit_max = spec.bpm_min / unit, spec.bpm_max / unit
    unit_typical = spec.bpm_typical / unit

    rows = np.where(
        (bpms_all >= unit_min * 0.95) & (bpms_all <= unit_max * 1.05)
    )[0]
    if len(rows) < 3:
        return np.full(max(tg.shape[1] // 8, 1), spec.bpm_typical)

    # Block-average columns to BLOCK_SEC resolution.
    blk = max(1, int(BLOCK_SEC * frame_rate))
    n_blocks = tg.shape[1] // blk
    if n_blocks < 2:
        return np.full(max(n_blocks, 1), spec.bpm_typical)
    # Keep neighbours of in-range rows so parabolic refinement has support.
    tgb = tg[:, : n_blocks * blk].reshape(tg.shape[0], n_blocks, blk).mean(axis=2)

    bpms = bpms_all[rows]
    prior = np.exp(-0.5 * (np.log2(bpms / unit_typical) / PRIOR_SIGMA_OCT) ** 2)

    # Harmonic reinforcement: a true tempo also shows periodicity at
    # bar/phrase-related lag multiples; accent-pattern artifacts (habanera
    # dotted rhythms) do not. Sum tempogram support before decoding.
    base = np.clip(tgb, 0.0, None)
    scores = np.zeros((len(rows), n_blocks))
    for mult, weight in spec.harmonics:
        idx = rows * mult
        valid = idx < base.shape[0]
        scores[valid, :] += weight * base[idx[valid], :]
    scores *= prior[:, None]

    path = _viterbi_tempo_path(scores, bpms)
    chosen = rows[path]

    # Parabolic interpolation around each chosen lag for sub-bin precision.
    r0 = np.clip(chosen, 1, tgb.shape[0] - 2)
    cols = np.arange(n_blocks)
    ym1, y0, yp1 = tgb[r0 - 1, cols], tgb[r0, cols], tgb[r0 + 1, cols]
    denom = ym1 - 2 * y0 + yp1
    with np.errstate(divide="ignore", invalid="ignore"):
        delta = np.where(np.abs(denom) > 1e-12, 0.5 * (ym1 - yp1) / denom, 0.0)
    delta = np.nan_to_num(np.clip(delta, -0.5, 0.5))
    lag_frac = np.clip(r0 + delta, 1e-3, None)
    curve = 60.0 * frame_rate / lag_frac * unit  # back to beat-level BPM

    # Median smoothing over ~SMOOTH_SEC.
    k = max(3, int(SMOOTH_SEC / BLOCK_SEC) | 1)
    if len(curve) > k:
        curve = scipy.signal.medfilt(curve, kernel_size=k)
    return curve


def analyze_tempo(
    y: np.ndarray,
    sr: int,
    spec: RhythmSpec,
    onset_env: np.ndarray | None = None,
) -> TempoResult:
    import librosa

    oenv = onset_env if onset_env is not None else librosa.onset.onset_strength(
        y=y, sr=sr, hop_length=HOP
    )

    curve = _local_tempo_curve(y, sr, spec)

    # Trim tempogram edge effects (half a window at each end) before stats.
    n_edge = int(TEMPOGRAM_WINDOW_SEC / 2 / BLOCK_SEC)
    inner = curve[n_edge:-n_edge] if len(curve) > 3 * n_edge else curve

    bpm_median = float(np.median(inner))
    bpm_low = float(np.percentile(inner, 10))
    bpm_high = float(np.percentile(inner, 90))

    # Stability is judged on the *detrended* curve: a gradual accelerando
    # (routine in golden-age valses) is still a fixed, danceable groove.
    # Only local push-pull (rubato) should count against it. The BPM range
    # above stays un-detrended — it reports the real drift.
    x = np.arange(len(inner), dtype=float)
    if len(inner) > 8:
        slope, intercept = np.polyfit(x, inner, 1)
        resid = inner - (slope * x + intercept)
    else:
        resid = inner - np.mean(inner)
    cv = float(np.std(resid) / max(np.mean(inner), 1e-6))
    stability = 100.0 / (1.0 + (cv / CV_HALF) ** 2)

    _, beats = librosa.beat.beat_track(
        onset_envelope=oenv, sr=sr, hop_length=HOP,
        bpm=bpm_median, tightness=100, units="frames",
    )
    beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=HOP)

    return TempoResult(
        bpm=round(bpm_median, 1),
        bpm_low=round(bpm_low, 1),
        bpm_high=round(bpm_high, 1),
        stability=round(stability, 1),
        tempo_cv=round(cv, 4),
        is_fixed_time=stability >= spec.fixed_threshold,
        beat_times=beat_times,
        onset_env=oenv,
        local_bpm=curve,
    )
