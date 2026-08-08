"""Tune the key detector against Mixed-In-Key ground truth in the file tags.

Sweeps chroma variant x aggregation x profile set x end-chord boost,
computing chroma once per file and evaluating all combos from cache.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compas_core.audio import load_audio

PITCH = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ENH = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#",
       "Cb": "B", "Fb": "E"}

PROFILES = {
    "KK": (
        np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]),
        np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]),
    ),
    "Temperley": (
        np.array([5.0, 2.0, 3.5, 2.0, 4.5, 4.0, 2.0, 4.5, 2.0, 3.5, 1.5, 4.0]),
        np.array([5.0, 2.0, 3.5, 4.5, 2.0, 4.0, 2.0, 4.5, 3.5, 2.0, 1.5, 4.0]),
    ),
    "Shaath": (
        np.array([6.6, 2.0, 3.5, 2.3, 4.6, 4.0, 2.5, 5.2, 2.4, 3.7, 2.3, 3.4]),
        np.array([6.5, 2.7, 3.5, 5.4, 2.6, 3.5, 2.5, 5.2, 4.0, 2.7, 4.3, 3.2]),
    ),
}

GROUND_TRUTH = {
    "Silueta": "Ebm",
    "Milonga De Mis Amores": "Am",
    "Danzarin": "G",
    "El Incendio": "Am",
    "Hotel Victoria": "Eb",
    "Amarras": "D",
    "Toda Mi Vida": "Dm",
    "Paisaje": "A",
    "Mi Novia De Ayer": "F",
}


def norm_key(k: str) -> tuple[int, bool]:
    minor = k.endswith("m")
    root = k[:-1] if minor else k
    root = ENH.get(root, root)
    return PITCH.index(root), minor


def chroma_variants(path: Path) -> dict:
    import librosa

    y, sr = load_audio(path)
    y_h = librosa.effects.harmonic(y)

    out = {}
    grams = {
        "cqt": librosa.feature.chroma_cqt(y=y_h, sr=sr),
        "cqt_c2_5o": librosa.feature.chroma_cqt(
            y=y_h, sr=sr, fmin=librosa.note_to_hz("C2"), n_octaves=5),
        "cens": librosa.feature.chroma_cens(y=y_h, sr=sr),
        "stft": librosa.feature.chroma_stft(y=y_h, sr=sr),
    }
    rms = librosa.feature.rms(y=y)[0]
    idx = np.where(rms > rms.max() * 0.05)[0]
    for name, c in grams.items():
        end_frame = min(idx[-1] if len(idx) else c.shape[1] - 1, c.shape[1] - 1)
        end_start = max(0, end_frame - int(12 * sr / 512))
        end = c[:, end_start:end_frame + 1].mean(axis=1)
        out[name] = {
            "mean": c.mean(axis=1),
            "median": np.median(c, axis=1),
            "end": end / max(end.max(), 1e-9),
        }
    return out


def predict(full, end, maj, min_, k_end):
    full = full / max(full.sum(), 1e-9)
    best, best_score = None, -1e9
    for template, minor in ((maj, False), (min_, True)):
        t = template / template.sum()
        for pc in range(12):
            corr = float(np.corrcoef(full, np.roll(t, pc))[0, 1])
            third = end[(pc + 3) % 12] if minor else end[(pc + 4) % 12]
            wrong = end[(pc + 4) % 12] if minor else end[(pc + 3) % 12]
            end_score = (0.5 * end[pc] + 0.25 * end[(pc + 7) % 12]
                         + 0.35 * third - 0.20 * wrong)
            score = corr + k_end * end_score
            if score > best_score:
                best_score, best = score, (pc, minor)
    return best


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "example_songs"
    files = {frag: next(f for f in root.rglob("*.flac") if frag in f.name)
             for frag in GROUND_TRUTH}

    print("computing chroma variants…", flush=True)
    feats = {frag: chroma_variants(p) for frag, p in files.items()}

    rows = []
    for chroma_name in ("cqt", "cqt_c2_5o", "cens", "stft"):
        for agg in ("mean", "median"):
            for prof_name, (maj, min_) in PROFILES.items():
                for k_end in (0.0, 0.35, 0.7):
                    hits, details = 0, []
                    for frag, truth in GROUND_TRUTH.items():
                        v = feats[frag][chroma_name]
                        pc, minor = predict(v[agg], v["end"], maj, min_, k_end)
                        got = PITCH[pc] + ("m" if minor else "")
                        ok = (pc, minor) == norm_key(truth)
                        hits += ok
                        details.append(f"{frag[:10]}:{got}{'+' if ok else '!'}")
                    rows.append((hits, chroma_name, agg, prof_name, k_end, details))

    rows.sort(key=lambda r: -r[0])
    for hits, cn, agg, pn, k_end, details in rows[:15]:
        print(f"{hits}/9  {cn:<10} {agg:<7} {pn:<10} k_end={k_end:<4} "
              + " ".join(details))


if __name__ == "__main__":
    main()
