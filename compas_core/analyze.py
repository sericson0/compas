"""Top-level analysis orchestration: one call per track.

``analyze_file(path)`` -> :class:`TrackAnalysis` with every metric the GUI,
CLI, and tag writer need.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from compas_core.audio import load_audio
from compas_core.energy import N_FFT, analyze_energy
from compas_core.harmony import analyze_harmony
from compas_core.key import analyze_key
from compas_core.loudness import analyze_loudness
from compas_core.rhythm import RHYTHM_SPECS, Rhythm, rhythm_from_genre
from compas_core.tags import FileTags, read_tags
from compas_core.tempo import HOP, analyze_tempo, compute_tempogram
from compas_core.texture import analyze_texture
from compas_core.vocal import analyze_vocal, vocal_hint_from_name

# Below this margin between the best and runner-up rhythm hypothesis, the
# audio-only guess is not trustworthy enough to act on silently.
RHYTHM_CONFIDENCE_FLOOR = 0.15

# Constant-Q settings. These are librosa's chroma_cqt defaults, restated
# here because we compute the CQT once and fold it into both a CQT chroma
# (for the key) and a CENS chroma (for harmonic variety) — passing the same
# tuning through reproduces chroma_cqt(y=...) bit for bit, so sharing it
# costs nothing and changes no key result.
BINS_PER_OCTAVE = 36
N_OCTAVES = 7


@dataclass
class TrackAnalysis:
    path: str
    filename: str
    title: str | None
    artist: str | None
    date: str | None
    duration_sec: float

    rhythm: str                # tango / vals / milonga
    rhythm_source: str         # override / genre-tag / audio / default
    rhythm_confidence: float   # 0-1; only meaningful when source == "audio"
    time_signature: str        # 4/4, 3/4, 2/4

    bpm: float                 # median beat-level BPM
    bpm_low: float
    bpm_high: float
    bars_per_min: float
    stability: float           # 0-100
    tempo_cv: float            # raw local-tempo variation (calibration aid)
    timing: str                # fixed / flexible

    key: str
    camelot: str
    key_confidence: float
    tag_bpm: str | None        # pre-existing BPM tag (MIK/Serato/...), if any
    tag_key: str | None        # pre-existing initial-key tag, if any

    energy: float              # 1-10
    drive: float               # 0-100, band-limited beat articulation
    syncopation: float         # 0-100, weight falling between beats
    articulation: float        # 0-100, high = detached/staccato
    percussiveness: float      # 0-100, high = percussive, low = sustained
    harmonic_variety: float    # 0-100, distinct harmonies used (provisional)

    vocal: str                 # instrumental / estribillo / vocal
    vocal_source: str          # title / audio
    vocal_score: float         # 0-100, non-metrical syllabic modulation
    vocal_fraction: float      # 0-1, share of the track that scores vocal
    vocal_confidence: float    # 0-1; only meaningful when source == "audio"

    lufs: float | None         # EBU R128 integrated loudness
    lra: float | None          # EBU R128 loudness range, LU
    sample_peak_db: float
    dynamic_range_db: float    # legacy RMS spread; LRA supersedes it
    onset_density: float
    raw_drive_low: float       # calibration aids
    raw_drive_mid: float
    raw_syncopation: float
    raw_loudness_var: float
    raw_attack_db: float
    raw_release_db: float
    raw_anisotropy: float
    raw_eff_rank: float
    raw_chord_change: float

    def to_dict(self) -> dict:
        return asdict(self)

    def facet_label(self, vocabulary: str = "english",
                    axis_keys=None) -> str:
        """Composed facet description, e.g. 'fast driving instrumental'."""
        from compas_core import facets

        return facets.label(
            self, vocabulary,
            facets.DEFAULT_AXIS_KEYS if axis_keys is None else axis_keys)

    def tag_fields(self, *, key_as_camelot: bool = False,
                   facet_vocabulary: str | None = None,
                   facet_axes=None) -> dict[str, str]:
        """Canonical tag fields for compas_core.tags.write_tags.

        ``facet_vocabulary`` adds a COMPAS_FACETS field with the composed
        label, which is the form worth browsing on in VirtualDJ.
        """
        fields = {
            "BPM": f"{self.bpm:.1f}",
            "INITIALKEY": self.camelot if key_as_camelot else self.key,
            "COMPAS_RHYTHM": self.rhythm,
            "COMPAS_ENERGY": f"{self.energy:.1f}",
            "COMPAS_DRIVE": f"{self.drive:.0f}",
            "COMPAS_SYNCOPATION": f"{self.syncopation:.0f}",
            "COMPAS_ARTICULATION": f"{self.articulation:.0f}",
            "COMPAS_TEXTURE": f"{self.percussiveness:.0f}",
            "COMPAS_HARMONY": f"{self.harmonic_variety:.0f}",
            "COMPAS_VOCAL": self.vocal,
            "COMPAS_STABILITY": f"{self.stability:.0f}",
            "COMPAS_TIMING": self.timing,
            "COMPAS_BPM_RANGE": f"{self.bpm_low:.0f}-{self.bpm_high:.0f}",
            "COMPAS_BARS_PER_MIN": f"{self.bars_per_min:.1f}",
            "COMPAS_DYNAMIC_RANGE_DB": f"{self.dynamic_range_db:.1f}",
        }
        if facet_vocabulary:
            fields["COMPAS_FACETS"] = self.facet_label(
                facet_vocabulary, facet_axes)
        if self.lufs is not None:
            fields["COMPAS_LUFS"] = f"{self.lufs:.1f}"
        if self.lra is not None:
            fields["COMPAS_LRA"] = f"{self.lra:.1f}"
        return fields


# --- rhythm detection from audio -----------------------------------------
#
# Each rhythm is treated as a hypothesis and tested on its own terms:
# beats are tracked *inside that rhythm's tempo range*, then the sequence
# of beat accent strengths is autocorrelated in the BEAT domain.
#
# The beat domain is the important part. In the lag domain, autocorrelation
# is high at every integer multiple of the beat period simply because the
# beat repeats, so "support at 3 beats" does not distinguish 3/4 from 4/4 --
# an earlier attempt scoring lag-domain multiples scored no better than the
# heuristic it replaced. Once the signal is sampled at beat positions,
# lag 3 versus lag 2/4 measures grouping directly.
#
# Tango and milonga are both duple and are not separable this way; the
# tempo prior distinguishes them, which is what it is good at.
#
# Step 1, ternary vs duple: at the candidate vals beat lag L, compare the
# autocorrelation at 3L against the midpoint of 2L and 4L. In 3/4 the bar
# falls on 3L, so it sits ABOVE its neighbours; in duple meter 3L is not a
# bar multiple and dips below. Taking the excess over neighbours is what
# makes this work -- raw support at 3L is high in every meter, because any
# integer multiple of the beat period correlates well.
#
# On the example corpus this separates cleanly: all four valses land
# positive (+0.006 to +0.047), all twelve tangos negative (-0.010 to
# -0.192), milongas negative except Silueta at +0.0035.
#
# Step 2, tango vs milonga: both are duple and produce identical grouping
# evidence, so only tempo separates them. One tempo pass with a wide duple
# probe, then compare against each genre's typical tempo.
#
_TERNARY_THRESHOLD = 0.005
_TEMPO_PRIOR = 0.35


def _best_tempo_in_range(acf: np.ndarray, frame_rate: float, spec) -> float:
    """Strongest beat tempo inside this rhythm's range, harmonically reinforced."""
    best_val, best_bpm = -1e9, spec.bpm_typical
    for bpm in np.arange(spec.bpm_min, spec.bpm_max + 0.5, 0.5):
        lag = 60.0 * frame_rate / bpm
        total = 0.0
        for mult, weight in spec.harmonics:
            i = int(round(lag * mult))
            if 0 <= i < len(acf):
                total += weight * float(acf[i])
        if total > best_val:
            best_val, best_bpm = total, float(bpm)
    return best_bpm


def _ternary_excess(acf: np.ndarray, lag: float) -> float:
    """Autocorrelation at 3x the beat lag, relative to 2x and 4x."""
    def at(x: float) -> float:
        i = int(round(x))
        return float(acf[i]) if 0 <= i < len(acf) else 0.0

    return at(3 * lag) - 0.5 * (at(2 * lag) + at(4 * lag))


def detect_rhythm_from_audio(
    y: np.ndarray, sr: int, oenv: np.ndarray,
    tempogram: np.ndarray | None = None,
) -> tuple[Rhythm, float]:
    """Rhythm from audio alone, with a 0-1 confidence.

    Replaces a heuristic that estimated one unconstrained tempo and then
    looked for a 3-beat accent period. That scored 74% and misread 3 of 4
    valses as milonga: the free tempo estimate landed an octave below the
    vals tactus, destroying the very periodicity it was testing for, after
    which a tempo-range comparison always favoured milonga.
    """
    import librosa

    from compas_core.rhythm import DUPLE_PROBE
    from compas_core.tempo import analyze_tempo

    frame_rate = sr / HOP
    acf = librosa.feature.tempogram(
        onset_envelope=oenv, sr=sr, hop_length=HOP).mean(axis=1)

    # --- step 1: ternary test at the vals-range lag -----------------------
    vals_spec = RHYTHM_SPECS[Rhythm.VALS]
    vals_bpm = _best_tempo_in_range(acf, frame_rate, vals_spec)
    excess = _ternary_excess(acf, 60.0 * frame_rate / vals_bpm)
    if excess > _TERNARY_THRESHOLD:
        # Scale the margin so a comfortable positive reads as confident.
        return Rhythm.VALS, round(float(np.clip(excess / 0.03, 0.0, 1.0)), 3)

    # --- step 2: duple, so tango vs milonga on tempo ----------------------
    bpm = analyze_tempo(y, sr, DUPLE_PROBE, onset_env=oenv,
                        tempogram=tempogram).bpm
    cost_tango = abs(math.log(bpm / RHYTHM_SPECS[Rhythm.TANGO].bpm_typical))
    cost_milonga = abs(math.log(bpm / RHYTHM_SPECS[Rhythm.MILONGA].bpm_typical))
    if cost_tango <= cost_milonga:
        rhythm, margin = Rhythm.TANGO, cost_milonga - cost_tango
    else:
        rhythm, margin = Rhythm.MILONGA, cost_tango - cost_milonga
    # A duple call is also less certain the closer the ternary test ran to
    # its threshold, so fold that in.
    ternary_margin = float(np.clip((_TERNARY_THRESHOLD - excess) / 0.02, 0.0, 1.0))
    confidence = float(np.clip(margin / 0.13, 0.0, 1.0)) * ternary_margin
    return rhythm, round(confidence, 3)


def resolve_rhythm(
    tags: FileTags,
    y: np.ndarray | None,
    oenv: np.ndarray | None,
    sr: int,
    override: str | Rhythm | None = None,
    tempogram: np.ndarray | None = None,
) -> tuple[Rhythm, str, float]:
    """Resolution order: explicit override > GENRE tag > audio heuristic."""
    if override and str(override) != "auto":
        return Rhythm(str(override)), "override", 1.0
    tagged = rhythm_from_genre(tags.genre)
    if tagged is not None:
        return tagged, "genre-tag", 1.0
    if y is not None and oenv is not None:
        rhythm, conf = detect_rhythm_from_audio(y, sr, oenv, tempogram)
        return rhythm, "audio", conf
    return Rhythm.TANGO, "default", 0.0


def _shared_chromas(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """(CQT chroma, CENS chroma) from a single constant-Q transform.

    ``chroma_cqt(y=...)`` and ``chroma_cens(y=...)`` each compute their own
    CQT, so asking for both doubles the most expensive step in the tonal
    path. Both accept a precomputed one; estimating the tuning exactly as
    they do internally makes the CQT chroma bit-identical to the old call,
    which is what keeps the key results from moving.
    """
    import librosa

    tuning = librosa.estimate_tuning(y=y, sr=sr,
                                     bins_per_octave=BINS_PER_OCTAVE)
    cqt = np.abs(librosa.cqt(
        y, sr=sr, hop_length=HOP, fmin=None,
        n_bins=N_OCTAVES * BINS_PER_OCTAVE,
        bins_per_octave=BINS_PER_OCTAVE, tuning=tuning))
    shared = dict(C=cqt, sr=sr, bins_per_octave=BINS_PER_OCTAVE,
                  n_octaves=N_OCTAVES, fmin=None, tuning=tuning)
    return (librosa.feature.chroma_cqt(**shared),
            librosa.feature.chroma_cens(**shared))


def analyze_file(
    path: str | Path,
    rhythm: str | Rhythm | None = None,
    fast: bool = False,
) -> TrackAnalysis:
    """Analyze one audio file. ``rhythm``: tango/vals/milonga/auto/None.

    ``fast`` skips harmonic/percussive separation, which is ~80% of the run
    time on a typical track. Only the key estimate and harmonic variety read
    the separated signal, so everything else is bit-identical either way;
    the key is then matched against the full mix and can differ on a
    minority of tracks (3 of 19 on the example corpus, with no net accuracy
    loss against the Mixed In Key labels there).
    """
    import librosa

    path = Path(path)
    tags = read_tags(path)
    y, sr = load_audio(path)
    duration = len(y) / sr

    oenv = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    # Built once and shared: the auto-detector's duple probe and the final
    # tempo pass both read it, and it is needed either way.
    tempogram = compute_tempogram(y, sr)
    resolved, source, confidence = resolve_rhythm(
        tags, y, oenv, sr, override=rhythm, tempogram=tempogram)
    spec = RHYTHM_SPECS[resolved]

    tempo = analyze_tempo(y, sr, spec, onset_env=oenv, tempogram=tempogram)

    # One magnitude STFT feeds drive, syncopation and the texture metrics;
    # one onset list feeds articulation and onset density.
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=N_FFT)
    onsets = librosa.onset.onset_detect(
        onset_envelope=oenv, sr=sr, hop_length=HOP)

    # Only the harmonic half is used (for key and harmony); effects.harmonic
    # skips the percussive inverse STFT that effects.hpss would also compute.
    y_tonal = y if fast else librosa.effects.harmonic(y)
    chroma, cens = _shared_chromas(y_tonal, sr)

    key = analyze_key(y_tonal, sr, chroma=chroma)
    harmony = analyze_harmony(cens, chroma, tempo.beat_times, sr, hop=HOP)
    energy = analyze_energy(y, sr, tempo, spec, S=S, onsets=onsets)
    texture = analyze_texture(S, freqs, onsets, sr)
    loud = analyze_loudness(y, sr)
    voc = analyze_vocal(
        y, sr, tempo.bpm,
        instrumental_hint=vocal_hint_from_name(path.name, tags.title))

    return TrackAnalysis(
        path=str(path),
        filename=path.name,
        title=tags.title,
        artist=tags.artist,
        date=tags.date,
        duration_sec=round(duration, 1),
        rhythm=resolved.value,
        rhythm_source=source,
        rhythm_confidence=confidence,
        time_signature=f"{spec.beats_per_bar}/4",
        bpm=tempo.bpm,
        bpm_low=tempo.bpm_low,
        bpm_high=tempo.bpm_high,
        bars_per_min=round(tempo.bpm / spec.beats_per_bar, 1),
        stability=tempo.stability,
        tempo_cv=tempo.tempo_cv,
        timing="fixed" if tempo.is_fixed_time else "flexible",
        key=key.key,
        camelot=key.camelot,
        key_confidence=key.confidence,
        tag_bpm=tags.existing_bpm,
        tag_key=tags.existing_key,
        energy=energy.energy,
        drive=energy.drive,
        syncopation=energy.syncopation,
        articulation=texture.articulation,
        percussiveness=texture.percussiveness,
        harmonic_variety=harmony.harmonic_variety,
        vocal=voc.vocal,
        vocal_source=voc.vocal_source,
        vocal_score=voc.vocal_score,
        vocal_fraction=voc.vocal_fraction,
        vocal_confidence=voc.vocal_confidence,
        lufs=loud.lufs,
        lra=loud.lra,
        sample_peak_db=loud.sample_peak_db,
        dynamic_range_db=energy.dynamic_range_db,
        onset_density=energy.onset_density,
        raw_drive_low=energy.raw_drive_low,
        raw_drive_mid=energy.raw_drive_mid,
        raw_syncopation=energy.raw_syncopation,
        raw_loudness_var=energy.raw_loudness_var,
        raw_attack_db=texture.raw_attack_db,
        raw_release_db=texture.raw_release_db,
        raw_anisotropy=texture.raw_anisotropy,
        raw_eff_rank=harmony.raw_eff_rank,
        raw_chord_change=harmony.raw_chord_change,
    )
