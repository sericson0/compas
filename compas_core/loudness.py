"""EBU R128 / ITU-R BS.1770 loudness.

Integrated loudness (LUFS) is the number to match levels on across a set:
it is what tells you a 1935 Canaro will land 4 dB quieter than a 1963
Pugliese long before you hear it happen on the floor.

Loudness range (LRA, EBU Tech 3342) replaces the naive RMS percentile
spread we used to report: same idea, but K-weighted, silence-gated, and
standardised so the number means the same thing in any other tool.

Caveat for shellac-era material, worth repeating in the UI: K-weighting
applies a high-shelf boost above ~2 kHz, which is exactly where surface
noise lives, and that noise is continuous so R128's gating does not remove
it. Expect LRA to read low on noisy transfers. Relative ordering across a
library stays meaningful; the absolute value is not comparable to a modern
master.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Below this duration BS.1770 gating has too few blocks to be meaningful.
MIN_DURATION_SEC = 3.0


@dataclass
class LoudnessResult:
    lufs: float | None       # integrated loudness, LUFS
    lra: float | None        # loudness range, LU
    sample_peak_db: float    # dBFS, for a crude clipping hint


def analyze_loudness(y: np.ndarray, sr: int) -> LoudnessResult:
    """Integrated loudness and loudness range for a mono signal."""
    import pyloudnorm as pyln

    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    peak_db = 20.0 * np.log10(peak) if peak > 0 else -np.inf

    if len(y) / sr < MIN_DURATION_SEC:
        return LoudnessResult(None, None, round(peak_db, 2))

    meter = pyln.Meter(sr)
    try:
        lufs = float(meter.integrated_loudness(y))
    except Exception:
        lufs = float("-inf")
    try:
        lra = float(meter.loudness_range(y))
    except Exception:
        lra = None

    # Digital silence and fully-gated signals come back as -inf.
    if not np.isfinite(lufs):
        return LoudnessResult(None, lra if lra is not None else None,
                              round(peak_db, 2))
    return LoudnessResult(
        lufs=round(lufs, 1),
        lra=round(lra, 1) if lra is not None and np.isfinite(lra) else None,
        sample_peak_db=round(peak_db, 2),
    )
