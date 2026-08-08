"""Test the audio-only rhythm auto-detection against folder ground truth.

This path has never actually been exercised: every example file carries a
GENRE tag, so resolve_rhythm() always short-circuits before reaching the
audio heuristic. Any file without a usable GENRE tag falls through to it,
so its accuracy matters and is currently unknown.

Compares two approaches:
  A) the shipped heuristic in compas_core.analyze._detect_rhythm_from_audio
  B) librosa.feature.tempogram_ratio, which scores tempogram energy at
     metrically related lag multiples and is the standard tool for
     duple-vs-triple discrimination.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compas_core.analyze import _detect_rhythm_from_audio
from compas_core.audio import load_audio
from compas_core.rhythm import RHYTHM_SPECS, Rhythm
from compas_core.tempo import HOP, analyze_tempo

FOLDER_TRUTH = {
    "tangos": Rhythm.TANGO,
    "tango-flexible-time": Rhythm.TANGO,
    "vals": Rhythm.VALS,
    "milonga": Rhythm.MILONGA,
}


def main() -> None:
    import librosa

    root = Path(__file__).resolve().parents[1] / "example_songs"
    files = sorted(root.rglob("*.flac"))

    print(f"{'track':<42} {'truth':<8} {'heuristic':<10} {'tg_ratio(2,3,4)':<24} ok")
    print("-" * 96)
    hits = 0
    feats = []
    for f in files:
        truth = FOLDER_TRUTH[f.parent.name]
        y, sr = load_audio(f)
        oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)

        got = _detect_rhythm_from_audio(oenv, sr)
        ok = got == truth
        hits += ok

        # tempogram_ratio at the tracked tempo: relative energy at lag
        # multiples 2, 3, 4. A triple meter should show a peak at 3.
        spec = RHYTHM_SPECS[truth]
        t = analyze_tempo(y, sr, spec, onset_env=oenv)
        tgr = librosa.feature.tempogram_ratio(
            onset_envelope=oenv, sr=sr, hop_length=HOP, bpm=t.bpm)
        prof = tgr.mean(axis=1)
        # rows correspond to factors 1..len(prof); grab 2,3,4
        r234 = [float(prof[i - 1]) if i - 1 < len(prof) else 0.0 for i in (2, 3, 4)]
        feats.append((truth, r234))

        print(f"{f.name[:42]:<42} {truth.value:<8} {got.value:<10} "
              f"{r234[0]:.3f} {r234[1]:.3f} {r234[2]:.3f}        {'ok' if ok else 'MISS'}")

    print()
    print(f"Shipped heuristic accuracy: {hits}/{len(files)} = {hits/len(files)*100:.0f}%")
    print()
    print("tempogram_ratio class means (does factor-3 separate vals?):")
    for rh in (Rhythm.TANGO, Rhythm.VALS, Rhythm.MILONGA):
        g = [f for t, f in feats if t == rh]
        if not g:
            continue
        a = np.array(g)
        print(f"  {rh.value:<8} n={len(g):<3} f2={a[:,0].mean():.3f}  "
              f"f3={a[:,1].mean():.3f}  f4={a[:,2].mean():.3f}   "
              f"f3/f2={a[:,1].mean()/max(a[:,0].mean(),1e-9):.2f}")


if __name__ == "__main__":
    main()
