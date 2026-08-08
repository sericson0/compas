"""Exploratory: test candidate new metrics on the example corpus.

Four candidates, chosen because each answers a question a tango DJ actually
asks and each is cheap to compute from features we already extract:

1. TUNING OFFSET (cents from A=440). 78rpm transfer speed varied; a transfer
   running fast is sharp, and its BPM is wrong by the same percentage. If
   this correlates with anything, it is a correction factor, not just a
   curiosity.

2. METRICAL ACCENT PROFILE -> marcato en dos vs marcato en cuatro. Average
   onset energy at each position in the bar, phase-aligned by maximizing
   accent variance. This is *the* tango style axis (D'Arienzo marks all
   four; Di Sarli leans on 1 and 3) and no standard MIR tool reports it.

3. SYNCOPATION INDEX = off-beat energy / on-beat energy. Separates milonga's
   habanera from tango's straight marking, and rhythmic from lyrical tango.

4. VOCAL PRESENCE. Validated against ground truth already in the filenames:
   "- Instrumental -" vs a singer's name. Tanda building depends on this.

FINDINGS (run of 2026-08-07 over the 19-track example corpus):

- SYNCOPATION INDEX works and is worth adopting. It is nearly free (beat
  times are already computed) and it orders the orchestras the way a
  dancer would: Biagi's El Incendio is the straightest at 0.19, Di Sarli's
  El Amanecer the most off-beat at 0.57, and two of the three milongas sit
  at 0.64 as the habanera predicts.

- MARCATO / METRICAL PROFILE fails as implemented, but the first diagnosis
  here was wrong on two counts and is corrected:

  (a) The reported ratio (beats 1+3)/(beats 2+4) INVERTS under a one-beat
      phase shift, so 0.82 and 1.22 are the same alternation depth in
      opposite phase -- El Flete "scoring lowest" was an artifact of that,
      not a musical result. The phase-INVARIANT quantity is max(r, 1/r),
      and it needs no downbeat detection at all. Recomputed that way the
      depths run 1.00 (Di Sarli, El Amanecer) to 1.22 (El Flete).
  (b) So downbeat tracking is NOT required for alternation depth. Which is
      just as well: madmom cannot be installed here (last release 2018,
      build fails on Python 3.13). beat_this or BeatNet are the live
      options if true downbeats are ever needed.

  It still does not work, though: even phase-corrected, full-band depths
  span only 1.00-1.22, and the ordering does not match the musicology
  (D'Arienzo/Biagi should read as marcato en cuatro, i.e. FLAT). The
  signal is too weak in a full-band onset envelope. See
  test_band_drive.py -- restricting to 150-400 Hz makes articulation
  strength jump out clearly, so a band-limited retry is the way forward.

- TUNING OFFSET is unvalidated. Values spread -22 to +44 cents, which is
  consistent with real transfer-speed error but equally consistent with
  estimator noise. Two tracks pinned at -50/-48 cents, i.e. wrapped
  against the estimator's half-semitone boundary, which is a bad sign.
  To validate: run it on two different transfers of the same recording.

- VOCAL PRESENCE via pyin fails: 58% accuracy against the filename ground
  truth, which is worse than always guessing "vocal" (63% base rate).
  Voiced-probability never exceeds 0.18 on any track -- bandoneon and
  violin occupy the same register as the singer on narrow-band mono
  recordings. Needs source separation or a trained classifier.

Run: python scripts/explore_new_metrics.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compas_core.audio import load_audio
from compas_core.rhythm import RHYTHM_SPECS, Rhythm
from compas_core.tempo import HOP, analyze_tempo


def tuning_offset_cents(y: np.ndarray, sr: int) -> float:
    """Deviation from A=440 equal temperament, in cents (-50..+50)."""
    import librosa

    return float(librosa.estimate_tuning(y=y, sr=sr) * 100.0)


def metrical_profile(oenv: np.ndarray, beat_times: np.ndarray, sr: int,
                     beats_per_bar: int) -> tuple[np.ndarray, float]:
    """Mean onset energy at each metrical position, best phase alignment.

    Returns (profile normalized to mean 1.0, marcato_ratio) where
    marcato_ratio = mean(odd-numbered beats) / mean(even-numbered beats)
    for 4/4 -- near 1.0 means all four beats marked equally (marcato en
    cuatro); well above 1.0 means weight on 1 and 3 (marcato en dos).
    """
    import librosa

    frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=HOP)
    frames = frames[(frames >= 0) & (frames < len(oenv))]
    if len(frames) < beats_per_bar * 4:
        return np.ones(beats_per_bar), 1.0
    strengths = oenv[frames]

    # NOTE: this phase search is the weak point. Without true downbeat
    # detection we pick the phase with the most accent contrast, which on
    # near-flat profiles is just noise. See the script docstring findings.
    best_prof, best_var = None, -1.0
    for phase in range(beats_per_bar):
        prof = np.array([
            strengths[(phase + i) % beats_per_bar::beats_per_bar].mean()
            for i in range(beats_per_bar)
        ])
        v = float(np.var(prof))
        if v > best_var:
            best_var, best_prof = v, prof
    prof = best_prof / max(best_prof.mean(), 1e-9)
    if beats_per_bar == 4:
        marcato = float((prof[0] + prof[2]) / max(prof[1] + prof[3], 1e-9))
    else:
        marcato = float(prof[0] / max(prof[1:].mean(), 1e-9))
    return prof, marcato


def syncopation_index(oenv: np.ndarray, beat_times: np.ndarray, sr: int) -> float:
    """Off-beat energy / on-beat energy. Higher = more syncopated."""
    import librosa

    if len(beat_times) < 8:
        return 0.0
    off = (beat_times[:-1] + beat_times[1:]) / 2
    bf = librosa.time_to_frames(beat_times, sr=sr, hop_length=HOP)
    of = librosa.time_to_frames(off, sr=sr, hop_length=HOP)
    bf = bf[(bf >= 0) & (bf < len(oenv))]
    of = of[(of >= 0) & (of < len(oenv))]
    return float(oenv[of].mean() / max(oenv[bf].mean(), 1e-9))


def vocal_presence(y: np.ndarray, sr: int) -> float:
    """Fraction of time a stable pitch sits in the human vocal range.

    Cheap proxy for 'is there a singer': run pyin over three 20 s excerpts
    from the middle of the track (tango vocals enter after an instrumental
    intro), restricted to 110-500 Hz, and report the voiced fraction.
    """
    import librosa

    dur = len(y) / sr
    if dur < 60:
        spans = [(dur * 0.4, dur * 0.6)]
    else:
        spans = [(dur * 0.35, dur * 0.35 + 20),
                 (dur * 0.55, dur * 0.55 + 20),
                 (dur * 0.75, dur * 0.75 + 20)]
    fracs = []
    for t0, t1 in spans:
        seg = y[int(t0 * sr):int(min(t1, dur) * sr)]
        if len(seg) < sr:
            continue
        # Harmonic part only: reduces false positives from surface noise.
        seg_h = librosa.effects.harmonic(seg)
        _, voiced, voiced_prob = librosa.pyin(
            seg_h, fmin=110.0, fmax=500.0, sr=sr,
            frame_length=2048, hop_length=512)
        # Require confident voicing, not just a pitch guess.
        fracs.append(float(np.mean(voiced_prob > 0.6)))
    return float(np.mean(fracs)) if fracs else 0.0


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "example_songs"
    files = sorted(root.rglob("*.flac"))
    folder_rhythm = {"tangos": Rhythm.TANGO, "tango-flexible-time": Rhythm.TANGO,
                     "vals": Rhythm.VALS, "milonga": Rhythm.MILONGA}

    print(f"{'track':<42} {'rhy':<8} {'cents':>6} {'profile':<26} "
          f"{'marc':>5} {'sync':>5} {'voc':>5} {'truth':<6}")
    print("-" * 116)
    rows = []
    for f in files:
        rh = folder_rhythm[f.parent.name]
        spec = RHYTHM_SPECS[rh]
        y, sr = load_audio(f)
        import librosa
        oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
        t = analyze_tempo(y, sr, spec, onset_env=oenv)

        cents = tuning_offset_cents(y, sr)
        prof, marc = metrical_profile(oenv, t.beat_times, sr, spec.beats_per_bar)
        sync = syncopation_index(oenv, t.beat_times, sr)
        voc = vocal_presence(y, sr)
        truth = "instr" if "- Instrumental -" in f.name else "vocal"

        profs = " ".join(f"{p:.2f}" for p in prof)
        print(f"{f.name[:42]:<42} {rh.value:<8} {cents:>+6.1f} {profs:<26} "
              f"{marc:>5.2f} {sync:>5.2f} {voc:>5.2f} {truth:<6}")
        rows.append((f.name, rh.value, cents, marc, sync, voc, truth))

    # --- does the vocal proxy actually separate the two classes? ---------
    print()
    inst = [r[5] for r in rows if r[6] == "instr"]
    voc_ = [r[5] for r in rows if r[6] == "vocal"]
    print(f"VOCAL PROXY  instrumental (n={len(inst)}): "
          f"{min(inst):.2f}-{max(inst):.2f} mean {np.mean(inst):.2f}")
    print(f"             vocal        (n={len(voc_)}): "
          f"{min(voc_):.2f}-{max(voc_):.2f} mean {np.mean(voc_):.2f}")
    # best threshold by simple scan
    best_t, best_acc = 0, 0
    for th in np.arange(0.05, 0.95, 0.01):
        acc = (sum(v < th for v in inst) + sum(v >= th for v in voc_)) / len(rows)
        if acc > best_acc:
            best_acc, best_t = acc, th
    print(f"             best threshold {best_t:.2f} -> accuracy "
          f"{best_acc*100:.0f}% ({round(best_acc*len(rows))}/{len(rows)})")

    print()
    print("MARCATO by orchestra (4/4 only, higher = weight on beats 1&3):")
    for name, rhy, _, marc, sync, _, _ in sorted(
            [r for r in rows if r[1] == "tango"], key=lambda r: -r[3]):
        print(f"   {marc:>5.2f}  sync {sync:>4.2f}  {name[:52]}")


if __name__ == "__main__":
    main()
