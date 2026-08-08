"""Test a band-resolved replacement for the current 'drive' metric.

The shipped drive metric is tempo-confounded (see the energy-vs-drive
analysis): it divides on-beat onset energy by the track's own mean, and at
vals tempos the attacks are dense enough to inflate that denominator.

Candidate replacement, adapted from Essentia's BeatsLoudness idea but
re-banded for shellac (which rolls off below ~150 Hz and above ~5 kHz, so
the usual 20 Hz and 7-22 kHz bands are empty or pure noise):

  low  150-400 Hz    bass/left-hand piano marking the compas
  mid  400-1200 Hz   bandoneon body
  high 1200-4000 Hz  attack transients, violin

For each band, on-beat energy / off-beat energy. A bass-articulated
marcato should show high low-band contrast; a legato orchestra that fills
between beats should show low contrast across all bands.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compas_core.audio import load_audio
from compas_core.rhythm import RHYTHM_SPECS, Rhythm
from compas_core.tempo import HOP, analyze_tempo

BANDS = [("low", 150, 400), ("mid", 400, 1200), ("high", 1200, 4000)]

FOLDER_RHYTHM = {"tangos": Rhythm.TANGO, "tango-flexible-time": Rhythm.TANGO,
                 "vals": Rhythm.VALS, "milonga": Rhythm.MILONGA}


def band_contrasts(y: np.ndarray, sr: int, beat_times: np.ndarray) -> list[float]:
    import librosa

    if len(beat_times) < 8:
        return [1.0] * len(BANDS)
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)

    off = (beat_times[:-1] + beat_times[1:]) / 2
    bf = librosa.time_to_frames(beat_times, sr=sr, hop_length=HOP)
    of = librosa.time_to_frames(off, sr=sr, hop_length=HOP)
    bf = bf[(bf >= 0) & (bf < S.shape[1])]
    of = of[(of >= 0) & (of < S.shape[1])]

    out = []
    for _, lo, hi in BANDS:
        rows = np.where((freqs >= lo) & (freqs < hi))[0]
        env = S[rows, :].sum(axis=0)
        # onset-style: positive first difference, so we measure attack not
        # sustained level (a legato orchestra is loud but not articulated)
        flux = np.maximum(0.0, np.diff(env, prepend=env[0]))
        on = flux[bf].mean()
        offv = flux[of].mean()
        out.append(float(on / max(offv, 1e-9)))
    return out


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "example_songs"
    files = sorted(root.rglob("*.flac"))
    import librosa

    print(f"{'track':<44} {'rhy':<8} {'low':>6} {'mid':>6} {'high':>6}")
    print("-" * 80)
    rows = []
    for f in files:
        rh = FOLDER_RHYTHM[f.parent.name]
        y, sr = load_audio(f)
        oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
        t = analyze_tempo(y, sr, RHYTHM_SPECS[rh], onset_env=oenv)
        c = band_contrasts(y, sr, t.beat_times)
        rows.append((f.name, rh.value, c))
        print(f"{f.name[:44]:<44} {rh.value:<8} {c[0]:>6.2f} {c[1]:>6.2f} {c[2]:>6.2f}")

    print()
    print("Class means (is this less rhythm-biased than the current drive?):")
    for rh in ("tango", "vals", "milonga"):
        g = np.array([c for _, r, c in rows if r == rh])
        print(f"  {rh:<8} n={len(g):<3} low {g[:,0].mean():.2f}  "
              f"mid {g[:,1].mean():.2f}  high {g[:,2].mean():.2f}")

    print()
    print("Tangos ranked by low-band (bass) articulation:")
    for name, r, c in sorted([r for r in rows if r[1] == "tango"],
                             key=lambda r: -r[2][0]):
        print(f"   low {c[0]:>5.2f}  mid {c[1]:>5.2f}  high {c[2]:>5.2f}  {name[:48]}")


if __name__ == "__main__":
    main()
