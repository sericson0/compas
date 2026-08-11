"""Musical key estimation: chroma profile matching + final-chord evidence.

Configuration chosen by sweeping against Mixed-In-Key ground truth on the
example corpus (scripts/key_experiment*.py): Krumhansl-Kessler profiles on
full-song CQT chroma, plus a boost from the last ~5 s of music — tango
recordings end on the tonic chord, which resolves the classic
tonic-vs-dominant confusion of whole-song profile matching.

Note for golden-age material: 78 rpm transfer speed was not always exact, so
recordings can sit noticeably between concert-pitch keys, and surface noise
blurs the chroma. Treat low-confidence keys as approximate; when a file
already carries a Mixed-In-Key tag, that value is surfaced alongside ours.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PITCH_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Kessler key profiles
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

END_WINDOW_SEC = 5.0
END_WEIGHT = 0.35

# Camelot wheel: (pitch class, is_minor) -> code
_CAMELOT_MAJOR = {0: "8B", 1: "3B", 2: "10B", 3: "5B", 4: "12B", 5: "7B",
                  6: "2B", 7: "9B", 8: "4B", 9: "11B", 10: "6B", 11: "1B"}
_CAMELOT_MINOR = {0: "5A", 1: "12A", 2: "7A", 3: "2A", 4: "9A", 5: "4A",
                  6: "11A", 7: "6A", 8: "1A", 9: "8A", 10: "3A", 11: "10A"}


@dataclass
class KeyResult:
    key: str          # e.g. "Dm" / "F"
    camelot: str      # e.g. "7A"
    is_minor: bool
    confidence: float  # 0-100


def analyze_key(y_harmonic: np.ndarray, sr: int,
                chroma: np.ndarray | None = None) -> KeyResult:
    """``chroma`` is the CQT chroma of ``y_harmonic``; pass it in when it has
    already been computed (analyze.py shares one CQT with harmony.py)."""
    import librosa

    if chroma is None:
        chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr)
    full = chroma.mean(axis=1)
    full = full / max(full.sum(), 1e-9)

    # Final-chord evidence: last END_WINDOW_SEC before the music stops.
    rms = librosa.feature.rms(y=y_harmonic)[0]
    n = min(chroma.shape[1], len(rms))
    above = np.where(rms[:n] > rms[:n].max() * 0.05)[0]
    end_frame = int(above[-1]) if len(above) else n - 1
    start = max(0, end_frame - int(END_WINDOW_SEC * sr / 512))
    end = chroma[:, start:end_frame + 1].mean(axis=1)
    end = end / max(end.max(), 1e-9)

    scores = []  # (score, pitch_class, is_minor)
    for template, is_minor in ((_MAJOR, False), (_MINOR, True)):
        t = template / template.sum()
        for pc in range(12):
            corr = float(np.corrcoef(full, np.roll(t, pc))[0, 1])
            score = corr + END_WEIGHT * (
                0.6 * end[pc] + 0.15 * end[(pc + 7) % 12])
            scores.append((score, pc, is_minor))
    scores.sort(reverse=True)

    best_s, pc, is_minor = scores[0]
    # Margin over the best *different-tonic* candidate -> confidence
    runner = next(s for s, p, m in scores[1:] if p != pc)
    confidence = float(np.clip((best_s - runner) * 350 + 40, 0, 100))

    name = PITCH_NAMES[pc] + ("m" if is_minor else "")
    camelot = (_CAMELOT_MINOR if is_minor else _CAMELOT_MAJOR)[pc]
    return KeyResult(key=name, camelot=camelot, is_minor=is_minor,
                     confidence=round(confidence, 0))
