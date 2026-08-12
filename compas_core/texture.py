"""Articulation and melodic/percussive texture.

Articulation
------------
How notes are *attacked and released*, which is a different question from
where their energy falls in the bar. ``energy.drive`` already answers the
latter (on-beat versus off-beat flux); articulation answers whether the
orchestra plays short and detached or long and joined-up, and the two
genuinely come apart -- Canaro's *Silueta Portena* marks the compas hard
(drive 61) with soft, rounded attacks, while Troilo's *Toda Mi Vida* is the
other way round.

Two quantities, both read off the melodic band (250-2500 Hz, where the
bandoneon and violins sit) at every detected onset:

    attack   dB risen over the 50 ms into the onset peak
    release  dB fallen from that peak within the next 140 ms

Both windows are *absolute*, not fractions of a beat. That is the whole
trick: a tempo-relative window would make any fast track look detached and
any slow one legato, which is the tempo confound that sank the first
version of drive (see energy.py).

Articulation and drive correlate at r = 0.73 across the example corpus --
related, as they should be, but with half the variance independent, and the
disagreements are the interesting ones: Victor's *Temo* marks the compas
firmly (drive 61) with the softest attacks in the corpus (articulation 5),
and Troilo's *Toda Mi Vida* is the reverse (drive 38, articulation 64).

Texture
-------
Sustained/melodic versus percussive, from the anisotropy of the
spectrogram: percussive energy changes fast along time and slowly along
frequency, harmonic energy the reverse. That is the same premise
harmonic/percussive source separation is built on, measured directly
instead of via two median filters and a mask.

    percussiveness = mean|dS/dt| / (mean|dS/dt| + mean|dS/df|)

Measured against a full-resolution ``librosa.decompose.hpss`` split on the
example corpus it holds rank order at Spearman 0.74 -- for 0.09 s/track
against 20 s/track. It also keeps the promise fast mode makes elsewhere:
this number does not depend on the harmonic separation, so it is identical
in both modes.

It is worth having because it is genuinely orthogonal to the marking
metrics: percussiveness correlates with drive at r = 0.06 across the
example corpus, so it adds an axis rather than restating one. The
surprising reading -- late Pugliese near the top -- is not an artifact:
the full HPSS split agrees, and the yumba really is a percussive attack.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from compas_core.tempo import HOP

# Melodic band for articulation: above the compas-marking bass, below the
# shellac rolloff.
MELODIC_BAND = (250.0, 2500.0)

ATTACK_WINDOW_SEC = 0.050
RELEASE_WINDOW_SEC = 0.140

# 0-100 anchors: 1st/99th percentile over an 11,948-track library
# (2026-08-11). The first version of these was fitted to a 19-track corpus
# and was too narrow at both ends -- it pinned 8.2% of attacks at 0 and
# 9.7% of anisotropies at 100, which is resolution thrown away exactly
# where the facet cuts need it. Re-fit with scripts/calibrate_facets.py,
# and re-fit the facet thresholds in the same pass: they are percentiles of
# the scale these anchors define, so moving one without the other silently
# reclassifies the library.
ATTACK_ANCHORS = (1.45, 8.27)
RELEASE_ANCHORS = (2.39, 8.87)
ARTICULATION_WEIGHTS = (0.5, 0.5)   # (attack, release)

PERCUSSIVE_ANCHORS = (0.346, 0.511)


@dataclass
class TextureResult:
    articulation: float      # 0-100, high = detached/staccato
    percussiveness: float    # 0-100, high = percussive; low = sustained
    raw_attack_db: float
    raw_release_db: float
    raw_anisotropy: float


def _norm(value: float, anchor: tuple[float, float]) -> float:
    lo, hi = anchor
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def analyze_texture(
    S: np.ndarray,
    freqs: np.ndarray,
    onsets: np.ndarray,
    sr: int,
) -> TextureResult:
    """``S`` is the magnitude STFT at ``HOP``; ``onsets`` are frame indices."""
    fps = sr / HOP

    # --- articulation ----------------------------------------------------
    rows = np.where((freqs >= MELODIC_BAND[0]) & (freqs < MELODIC_BAND[1]))[0]
    attack_db = release_db = 0.0
    if len(rows) and len(onsets) >= 8:
        env = 20 * np.log10(np.clip(S[rows, :].sum(axis=0), 1e-8, None))
        pre = int(round(ATTACK_WINDOW_SEC * fps))
        post = int(round(RELEASE_WINDOW_SEC * fps))
        attacks, releases = [], []
        for f in onsets:
            if f - pre < 0 or f + post >= len(env):
                continue
            peak = env[f:f + 3].max()
            attacks.append(peak - env[f - pre])
            releases.append(peak - env[f + 3:f + post].min())
        if attacks:
            attack_db = float(np.mean(attacks))
            release_db = float(np.mean(releases))

    wa, wr = ARTICULATION_WEIGHTS
    articulation = 100.0 * (wa * _norm(attack_db, ATTACK_ANCHORS)
                            + wr * _norm(release_db, RELEASE_ANCHORS))

    # --- texture ---------------------------------------------------------
    if S.shape[0] > 1 and S.shape[1] > 1:
        dt = float(np.abs(np.diff(S, axis=1)).mean())
        df = float(np.abs(np.diff(S, axis=0)).mean())
        aniso = dt / max(dt + df, 1e-12)
    else:
        aniso = 0.5
    percussiveness = 100.0 * _norm(aniso, PERCUSSIVE_ANCHORS)

    return TextureResult(
        articulation=round(articulation, 0),
        percussiveness=round(percussiveness, 0),
        raw_attack_db=round(attack_db, 2),
        raw_release_db=round(release_db, 2),
        raw_anisotropy=round(aniso, 4),
    )
