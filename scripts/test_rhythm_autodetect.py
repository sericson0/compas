"""Test audio-only rhythm auto-detection against folder ground truth.

This path is invisible in normal use: every example file carries a GENRE
tag, so resolve_rhythm() short-circuits before reaching the audio
heuristic. Any file *without* a usable GENRE tag falls through to it, so
its accuracy matters. Run this after touching detect_rhythm_from_audio.

Baseline to beat: the original heuristic scored 14/19 (74%) and misread
3 of 4 valses as milonga.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compas_core.analyze import RHYTHM_CONFIDENCE_FLOOR, detect_rhythm_from_audio
from compas_core.audio import load_audio
from compas_core.rhythm import Rhythm
from compas_core.tempo import HOP

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

    print(f"{'track':<44} {'truth':<8} {'detected':<8} {'conf':>5}  result")
    print("-" * 84)
    hits = 0
    per_class: dict[str, list[bool]] = {}
    low_conf = 0
    for f in files:
        truth = FOLDER_TRUTH[f.parent.name]
        y, sr = load_audio(f)
        oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
        got, conf = detect_rhythm_from_audio(y, sr, oenv)
        ok = got == truth
        hits += ok
        per_class.setdefault(truth.value, []).append(ok)
        flag = "" if conf >= RHYTHM_CONFIDENCE_FLOOR else " (low conf)"
        if conf < RHYTHM_CONFIDENCE_FLOOR:
            low_conf += 1
        print(f"{f.name[:44]:<44} {truth.value:<8} {got.value:<8} {conf:>5.2f}  "
              f"{'ok' if ok else 'MISS'}{flag}")

    print()
    print(f"Overall: {hits}/{len(files)} = {hits/len(files)*100:.0f}%  "
          f"(baseline 14/19 = 74%)")
    for cls, res in sorted(per_class.items()):
        print(f"  {cls:<8} {sum(res)}/{len(res)}")
    print(f"Flagged low-confidence (<{RHYTHM_CONFIDENCE_FLOOR}): {low_conf}")


if __name__ == "__main__":
    main()
