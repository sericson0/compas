"""Key detector round 2: end-window length x bass-register end chroma.

The final chord of a tango states the tonic, but it is short; long end
windows are dominated by the preceding dominant harmony. Test short windows
and bass-only chroma (the double bass plays the root at the final chord).
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

KK_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

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


def features(path: Path) -> dict:
    import librosa

    y, sr = load_audio(path)
    y_h = librosa.effects.harmonic(y)
    full_c = librosa.feature.chroma_cqt(y=y_h, sr=sr)
    bass_c = librosa.feature.chroma_cqt(
        y=y_h, sr=sr, fmin=librosa.note_to_hz("C1"), n_octaves=3)

    rms = librosa.feature.rms(y=y)[0]
    idx = np.where(rms > rms.max() * 0.05)[0]
    end_frame = int(idx[-1]) if len(idx) else full_c.shape[1] - 1
    end_frame = min(end_frame, full_c.shape[1] - 1, bass_c.shape[1] - 1)

    out = {"full": full_c.mean(axis=1)}
    for sec in (2.5, 5.0, 10.0):
        s = max(0, end_frame - int(sec * sr / 512))
        for name, c in (("fullc", full_c), ("bass", bass_c)):
            seg = c[:, s:end_frame + 1].mean(axis=1)
            out[f"end_{name}_{sec}"] = seg / max(seg.max(), 1e-9)
    return out


def predict(full, end, k_end, third_w):
    full = full / max(full.sum(), 1e-9)
    best, best_score = None, -1e9
    for template, minor in ((KK_MAJ, False), (KK_MIN, True)):
        t = template / template.sum()
        for pc in range(12):
            corr = float(np.corrcoef(full, np.roll(t, pc))[0, 1])
            third = end[(pc + 3) % 12] if minor else end[(pc + 4) % 12]
            wrong = end[(pc + 4) % 12] if minor else end[(pc + 3) % 12]
            end_score = (0.6 * end[pc] + 0.15 * end[(pc + 7) % 12]
                         + third_w * (third - wrong))
            score = corr + k_end * end_score
            if score > best_score:
                best_score, best = score, (pc, minor)
    return best


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "example_songs"
    files = {frag: next(f for f in root.rglob("*.flac") if frag in f.name)
             for frag in GROUND_TRUTH}
    print("computing features…", flush=True)
    feats = {frag: features(p) for frag, p in files.items()}

    rows = []
    for endname in [k for k in next(iter(feats.values())) if k.startswith("end_")]:
        for k_end in (0.35, 0.7, 1.0):
            for third_w in (0.0, 0.3):
                hits, details = 0, []
                for frag, truth in GROUND_TRUTH.items():
                    pc, minor = predict(
                        feats[frag]["full"], feats[frag][endname], k_end, third_w)
                    got = PITCH[pc] + ("m" if minor else "")
                    ok = (pc, minor) == norm_key(truth)
                    hits += ok
                    details.append(f"{frag[:10]}:{got}{'+' if ok else '!'}")
                rows.append((hits, endname, k_end, third_w, details))

    rows.sort(key=lambda r: -r[0])
    for hits, endname, k_end, third_w, details in rows[:14]:
        print(f"{hits}/9  {endname:<14} k_end={k_end:<4} third_w={third_w:<4} "
              + " ".join(details))


if __name__ == "__main__":
    main()
