"""Vocal presence: instrumental, estribillo, or sung.

Why the obvious approaches fail here
------------------------------------
A monophonic pitch tracker (pyin) scored 58% against filename ground truth
on the example corpus -- worse than always guessing "vocal" -- because it
assumes one sounding pitch and a tango orchestra never offers one. Vibrato
detection is not much better: on narrow-band mono the violins vibrate in
the singer's register too, and a bandoneon, being a free-reed instrument,
can barely vibrate at all, so the cue separates *sections*, not voices.

What works: syllabic modulation, off the beat grid
--------------------------------------------------
A singer's syllable rate lands in the classic 2.5-7.5 Hz speech band. So
does a tango orchestra's note rate -- eighth notes at 130 BPM are 4.3 Hz --
which is why plain 4 Hz modulation energy (Scheirer & Slaney's
speech/music feature) is useless on this material.

The difference is that the orchestra's modulation is *locked to the beat*
and the singer's is not. We already know the tempo to a fraction of a BPM,
so the metrical comb can simply be notched out of the modulation spectrum
and whatever syllabic energy remains is the vocal evidence:

1. 40 mel bands over 200-3000 Hz (vocal fundamentals through F2), log,
   per-band mean removed.
2. Modulation spectrum of each band envelope over 14 s Hann windows.
   Long windows are not incidental -- at 6 s the modulation resolution is
   0.17 Hz and the notches eat most of the syllabic band with them.
3. Notch +/-0.18 Hz around the beat rate and its multiples.
4. Score = surviving 2.5-7.5 Hz energy over total 0.5-12 Hz energy, taken
   as the 70th percentile over windows, because tango vocals arrive after
   an instrumental introduction and a mean would dilute them.

Validation status
-----------------
Scored on an 11,948-track library (2026-08-11) whose filenames carry ground
truth: 3,421 marked "Instrumental" against 8,527 not, a 71% base rate.

**Overall: d' = 1.03, 80% correct.** That is nine points over the base
rate, and it is much weaker than the 19-track example corpus advertised
(d' = 2.0). The small corpus was not wrong so much as unrepresentative --
it was all 1935-1963 material, which is exactly where this method works.

The honest summary is that accuracy depends on era and rhythm, and the
averages hide both:

    era          n      d'     correct        rhythm     n      d'    correct
    pre-1930   1296   +0.43      66%          tango    9896   +1.26     80%
    1930-34    1000   +0.82      86%          vals     1126   +0.23     85%
    1935-39     983   +0.59      78%          milonga   926   +0.98     84%
    1940-44    2298   +1.71      91%
    1945-49    1397   +2.49      93%       (base rates: tango 69%,
    1950-59    2103   +2.23      91%        vals 85%, milonga 84%)
    1960+      2762   +0.44      76%

Read that as: **trust it on tango from 1940-1959** (91-93%), treat it as a
hint elsewhere, and note that on vals and milonga it barely beats guessing
the majority class -- those repertoires are 84-85% vocal to begin with, so
there is little for it to add.

Two caveats on the table itself. The 1960+ row is polluted by reissue dates
-- the library's tags run to 2023, so remastered golden-age sides land
there. And "vocal" only means "the filename does not say instrumental", so
an untagged instrumental counts as a detector error when it is really a
labelling gap.

The failure mode is musically coherent: a cantabile instrumental solo looks
like a singer, which is what the early era is full of.

Where a filename says "Instrumental" that answer is used and this estimate
is only reported. Re-fit on your own collection with
``scripts/validate_vocal.py``; ``scripts/rescore_vocal.py`` recomputes just
these columns of an existing library CSV, so retuning does not cost a full
re-analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from compas_core.tempo import HOP

# Male golden-age singers sit at f0 ~100-350 Hz with F1/F2 up to ~1800, so
# this window is the voice and little else. The original 200-3000 Hz was
# wider on the theory that more formant range must help; on a real library
# it does not, because above ~2 kHz a shellac transfer is mostly surface
# noise. Narrowing improved every slice at once -- see the module docstring.
MEL_BAND = (150.0, 2000.0)
N_MELS = 40
N_FFT = 2048

# Percentile of the per-window curve used as the track score. Tango vocals
# arrive after an instrumental introduction, so a mean dilutes them; the
# estribillo era (roughly 1924-34) is more extreme still, one refrain of a
# three-minute side. p85 beat p70 on early and golden-age material alike.
SCORE_PERCENTILE = 85

WINDOW_SEC = 14.0
NOTCH_HZ = 0.18
SYLLABIC_BAND = (2.5, 7.5)
REFERENCE_BAND = (0.5, 12.0)

# Beat-rate multiples notched out of the modulation spectrum.
METRICAL_MULTIPLES = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0,
                      4.0, 5.0, 6.0, 8.0)

# Fitted on 11,948 tracks. The global optimum is 13.8 (80.3%) and this is
# 14.2 (80.1%) on purpose: 14.22 is the optimum for 1935-1955 material,
# which is both where the method actually works and what gets played, and
# giving up 0.2 points overall to be right there is the better trade. The
# curve is flat between them either way -- 25 tracks in 11,948.
VOCAL_THRESHOLD = 14.2      # on the 0-100 score
# Above the threshold but singing for only part of the track = estribillo
# (a refrain). Untested rather than merely provisional: the example corpus
# contains no labelled estribillo, so this cut is set to the value at which
# the corpus produces none -- every full vocal in it runs 0.26 or higher.
# At 0.45 it fired on Di Sarli's *Nada* and Donato's *Carnaval De Mi
# Barrio*, both sung most of the way through. Until it is calibrated, read
# "estribillo" as "vocal, possibly brief".
ESTRIBILLO_MAX_FRACTION = 0.25

_INSTRUMENTAL_RE = re.compile(r"\binstrumental\b", re.IGNORECASE)


@dataclass
class VocalResult:
    vocal: str               # instrumental / estribillo / vocal
    vocal_source: str        # title / audio
    vocal_score: float       # 0-100, non-metrical syllabic modulation
    vocal_fraction: float    # 0-1, share of windows scoring above threshold
    vocal_confidence: float  # 0-1; only meaningful when source == "audio"


def vocal_hint_from_name(*fields: str | None) -> bool:
    """True when a filename or title says the track is instrumental.

    Deliberately one-directional: the word being present is reliable, its
    absence proves nothing (plenty of instrumentals are simply untagged).
    """
    return any(f and _INSTRUMENTAL_RE.search(f) for f in fields)


def _modulation_curve(y: np.ndarray, sr: int, bpm: float) -> np.ndarray:
    import librosa

    fps = sr / HOP
    mel = librosa.feature.melspectrogram(
        y=y, sr=sr, n_fft=N_FFT, hop_length=HOP, n_mels=N_MELS,
        fmin=MEL_BAND[0], fmax=MEL_BAND[1])
    L = np.log(np.clip(mel, 1e-10, None))
    L -= L.mean(axis=1, keepdims=True)

    n_per = int(WINDOW_SEC * fps)
    if L.shape[1] < n_per:                      # short track: one window
        n_per = L.shape[1]
    if n_per < int(4 * fps):
        return np.zeros(1)
    step = max(1, n_per // 3)

    win = np.hanning(n_per)
    mfreq = np.fft.rfftfreq(n_per, d=1.0 / fps)

    beat_hz = max(bpm, 1.0) / 60.0
    notched = np.zeros_like(mfreq, dtype=bool)
    for mult in METRICAL_MULTIPLES:
        notched |= np.abs(mfreq - beat_hz * mult) < NOTCH_HZ
    syllabic = ((mfreq >= SYLLABIC_BAND[0]) & (mfreq <= SYLLABIC_BAND[1])
                & ~notched)
    reference = (mfreq >= REFERENCE_BAND[0]) & (mfreq <= REFERENCE_BAND[1])
    if not syllabic.any():
        return np.zeros(1)

    vals = []
    for a in range(0, L.shape[1] - n_per + 1, step):
        spec = np.abs(np.fft.rfft(L[:, a:a + n_per] * win, axis=1)) ** 2
        vals.append(spec[:, syllabic].sum() / max(spec[:, reference].sum(), 1e-12))
    return np.array(vals) if vals else np.zeros(1)


def analyze_vocal(
    y: np.ndarray,
    sr: int,
    bpm: float,
    instrumental_hint: bool = False,
) -> VocalResult:
    """``instrumental_hint``: the filename/title already says instrumental."""
    curve = _modulation_curve(y, sr, bpm) * 100.0
    score = float(np.percentile(curve, SCORE_PERCENTILE))
    fraction = float(np.mean(curve >= VOCAL_THRESHOLD))

    if instrumental_hint:
        return VocalResult("instrumental", "title", round(score, 1),
                           round(fraction, 3), 1.0)

    if score < VOCAL_THRESHOLD:
        label = "instrumental"
    elif fraction < ESTRIBILLO_MAX_FRACTION:
        label = "estribillo"
    else:
        label = "vocal"

    # Confidence from distance to the threshold, in units of the class
    # separation observed on the corpus (means 12.6 and 17.3, so ~4.7).
    confidence = float(np.clip(abs(score - VOCAL_THRESHOLD) / 4.7, 0.0, 1.0))
    return VocalResult(label, "audio", round(score, 1), round(fraction, 3),
                       round(confidence, 3))
