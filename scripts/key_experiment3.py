"""Key detector round 3: robust end-of-music detection + separate mode vote.

Hypotheses:
1. The 'final chord' window sometimes lands in the shellac noise tail
   because rms > 5%-of-peak is too permissive -> use onset-based endpoint.
2. Root detection is decent but KK-minor misfits tango's harmonic minor ->
   pick the root with profiles, then decide major/minor by directly
   comparing third strengths (full song + ending).
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
    c = librosa.feature.chroma_cqt(y=y_h, sr=sr)

    rms = librosa.feature.rms(y=y)[0]
    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    n = min(c.shape[1], len(rms), len(oenv))

    ends = {
        "rms5max": int(np.max(np.where(rms[:n] > rms.max() * 0.05)[0])),
        "rms25p95": int(np.max(np.where(
            rms[:n] > np.percentile(rms[:n], 95) * 0.25)[0])),
        "onset": int(np.max(np.where(
            oenv[:n] > np.percentile(oenv[:n][oenv[:n] > 0], 90) * 0.2)[0])),
    }
    out = {"full": c.mean(axis=1)}
    for name, ef in ends.items():
        for sec in (2.5, 5.0):
            s = max(0, ef - int(sec * sr / 512))
            seg = c[:, s:ef + 1].mean(axis=1)
            out[f"end_{name}_{sec}"] = seg / max(seg.max(), 1e-9)
    return out


def predict_joint(full, end, k_end):
    """Round-2 style: root and mode chosen together."""
    fulln = full / max(full.sum(), 1e-9)
    best, best_score = None, -1e9
    for template, minor in ((KK_MAJ, False), (KK_MIN, True)):
        t = template / template.sum()
        for pc in range(12):
            corr = float(np.corrcoef(fulln, np.roll(t, pc))[0, 1])
            score = corr + k_end * (0.6 * end[pc] + 0.15 * end[(pc + 7) % 12])
            if score > best_score:
                best_score, best = score, (pc, minor)
    return best


def predict_split(full, end, k_end, mode_end_w):
    """Root from best-of-both-profiles, mode from third comparison."""
    fulln = full / max(full.sum(), 1e-9)
    root_score = np.full(12, -1e9)
    for template in (KK_MAJ, KK_MIN):
        t = template / template.sum()
        for pc in range(12):
            corr = float(np.corrcoef(fulln, np.roll(t, pc))[0, 1])
            s = corr + k_end * (0.6 * end[pc] + 0.15 * end[(pc + 7) % 12])
            root_score[pc] = max(root_score[pc], s)
    pc = int(np.argmax(root_score))
    fullm = full / max(full.max(), 1e-9)
    minor_ev = fullm[(pc + 3) % 12] + mode_end_w * end[(pc + 3) % 12]
    major_ev = fullm[(pc + 4) % 12] + mode_end_w * end[(pc + 4) % 12]
    return pc, minor_ev > major_ev


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "example_songs"
    files = {frag: next(f for f in root.rglob("*.flac") if frag in f.name)
             for frag in GROUND_TRUTH}
    print("computing features…", flush=True)
    feats = {frag: features(p) for frag, p in files.items()}

    end_names = [k for k in next(iter(feats.values())) if k.startswith("end_")]
    rows = []
    for endname in end_names:
        for k_end in (0.35, 0.7):
            for method, fn, extra in (
                ("joint", predict_joint, [None]),
                ("split", predict_split, [0.5, 1.0]),
            ):
                for ex in extra:
                    hits, details = 0, []
                    for frag, truth in GROUND_TRUTH.items():
                        f = feats[frag]
                        if method == "joint":
                            pc, minor = fn(f["full"], f[endname], k_end)
                        else:
                            pc, minor = fn(f["full"], f[endname], k_end, ex)
                        got = PITCH[pc] + ("m" if minor else "")
                        ok = (pc, minor) == norm_key(truth)
                        hits += ok
                        details.append(f"{frag[:10]}:{got}{'+' if ok else '!'}")
                    rows.append((hits, endname, k_end, method, ex, details))

    rows.sort(key=lambda r: -r[0])
    for hits, endname, k_end, method, ex, details in rows[:16]:
        print(f"{hits}/9  {endname:<15} k_end={k_end:<4} {method}"
              f"({ex})  " + " ".join(details))


if __name__ == "__main__":
    main()
