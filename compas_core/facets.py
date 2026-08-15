"""Facet grid: continuous metrics turned into words.

Each axis is one thresholded number that COMPAS already reports, rendered
in one of two vocabularies:

    english   fast / driving / staccato / steady / instrumental
    tango     rápido / rítmico / picado / compás / instrumental

Nothing here is a new measurement, and that is the point. A facet is a
*view* of a column, so a label that reads wrong is a threshold to argue
with rather than a claim to debug, and the number it came from is still
sitting in the next column over.

Composing a label
-----------------
``label()`` skips each axis's neutral level, so a track that is merely
average on an axis does not spend a word saying so: a driving fast
instrumental reads "fast driving instrumental", not "fast driving
mixed balanced steady instrumental". Per-axis columns still show every
level, neutral included.

Thresholds
----------
Calibrated on an 11,948-track tango library (2026-08-11) at the 25th and
75th percentile, so half of any collection reads as unremarkable on a given
axis and skips the word, while a quarter earns each outer term.

They replace a first set fitted to the 19-track example corpus, which was
wrong almost everywhere -- drive was cut at (30, 60) against a real (16,
50), and harmony at (45, 80) against (45, 72) once its anchors stopped
clipping a fifth of the library at 100.

Two things to know before re-fitting:

* the cuts are percentiles of the 0-100 scales defined by the anchors in
  ``texture.py`` and ``harmony.py``, so those must be re-fitted in the same
  pass -- ``scripts/calibrate_facets.py`` does both, in that order;
* the rhythms do not share a distribution. Median drive runs milonga 12 /
  tango 32 / vals 23, and median harmony 59 / 79 / 64. One set of cuts for
  all three is a deliberate compromise, and a large enough collection would
  justify per-rhythm thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from compas_core.rhythm import RHYTHM_SPECS, Rhythm

ENGLISH = "english"
TANGO = "tango"
VOCABULARIES = (ENGLISH, TANGO)


@dataclass(frozen=True)
class Axis:
    key: str
    name: str                                   # column header
    value: Callable[[Any], float | None]        # underlying number
    thresholds: tuple[float, ...]               # ascending cut points
    labels: Mapping[str, tuple[str, ...]]       # vocabulary -> level names
    help: str
    neutral: int | None = None                  # level omitted from labels
    default: bool = False                       # in the default selection
    # Levels are named classes, not cut points on a continuum. Calibration
    # must leave these alone: fitting percentiles to Voice's 0/1/2 produces
    # thresholds of (0, 2), which silently reclassifies every instrumental.
    categorical: bool = False


def _tempo_rel(a: Any) -> float | None:
    try:
        spec = RHYTHM_SPECS[Rhythm(a.rhythm)]
    except (ValueError, KeyError):
        return None
    return a.bpm / spec.bpm_typical


# Vocal presence is disabled — see compas_core/analyze.py for why.
# def _vocal_level(a: Any) -> float | None:
#     return {"instrumental": 0.0, "estribillo": 1.0,
#             "vocal": 2.0}.get(a.vocal)


AXES: tuple[Axis, ...] = (
    Axis(
        key="tempo", name="Tempo", value=_tempo_rel,
        thresholds=(0.99, 1.05),
        labels={ENGLISH: ("slow", "medium", "fast"),
                TANGO: ("lento", "medio", "rápido")},
        neutral=1, default=True,
        help="Tempo relative to what is typical for this rhythm, so a vals "
             "at 210 BPM is not automatically 'fast'. BPM divided by the "
             "genre's typical tempo; cuts at 0.99 and 1.05.",
    ),
    Axis(
        key="drive", name="Character", value=lambda a: a.drive,
        thresholds=(16.0, 50.0),
        labels={ENGLISH: ("smooth", "balanced", "driving"),
                TANGO: ("melódico", "intermedio", "rítmico")},
        neutral=1, default=True,
        help="The classic tango axis, from Drive: how hard the compas is "
             "marked. Melódico below 16, rítmico from 50.",
    ),
    Axis(
        key="articulation", name="Articulation",
        value=lambda a: a.articulation,
        thresholds=(27.0, 55.0),
        labels={ENGLISH: ("legato", "detached", "staccato"),
                TANGO: ("ligado", "medio", "picado")},
        neutral=1,
        help="How notes are attacked and released, from Articulation. "
             "Independent of Character: an orchestra can mark the compas "
             "hard with soft attacks, or play lightly with crisp ones.",
    ),
    Axis(
        key="texture", name="Texture", value=lambda a: a.percussiveness,
        thresholds=(41.0, 70.0),
        labels={ENGLISH: ("sustained", "mixed", "percussive"),
                TANGO: ("lírico", "equilibrado", "percusivo")},
        neutral=1,
        help="Melodic/sustained versus percussive, from Texture "
             "(spectrogram anisotropy). Bowed strings and held bandoneon "
             "chords sit low; piano and staccato marking sit high.",
    ),
    Axis(
        key="syncopation", name="Placement", value=lambda a: a.syncopation,
        thresholds=(39.0, 51.0),
        labels={ENGLISH: ("straight", "mixed", "syncopated"),
                TANGO: ("liso", "medio", "sincopado")},
        neutral=1,
        help="Where the weight falls, from Sync. Milonga's habanera and "
             "Di Sarli's off-beat weight score high; Biagi's straight "
             "marking scores low.",
    ),
    Axis(
        key="timing", name="Phrasing",
        value=lambda a: 1.0 if a.timing == "flexible" else 0.0,
        thresholds=(0.5,),
        labels={ENGLISH: ("steady", "flexible"),
                TANGO: ("compás", "fraseo")},
        neutral=0, default=True, categorical=True,
        help="From Timing: steady enough to dance without surprises, or "
             "noticeable rubato. Steady is the unmarked case, so it is "
             "left out of the composed label.",
    ),
    # Vocal presence is disabled — see compas_core/analyze.py for why.
    # Axis(
    #     key="vocal", name="Voice", value=_vocal_level,
    #     thresholds=(0.5, 1.5),
    #     labels={ENGLISH: ("instrumental", "refrain", "vocal"),
    #             TANGO: ("instrumental", "estribillo", "cantado")},
    #     neutral=None, default=True, categorical=True,
    #     help="Instrumental, a refrain (estribillo), or sung throughout. "
    #          "Taken from the filename when it says 'instrumental', "
    #          "otherwise estimated from the audio.",
    # ),
    Axis(
        key="harmony", name="Harmony", value=lambda a: a.harmonic_variety,
        thresholds=(45.0, 72.0),
        labels={ENGLISH: ("simple", "moderate", "complex"),
                TANGO: ("directo", "elaborado", "complejo")},
        neutral=1,
        help="How many distinct harmonies the piece uses, from Harmony. "
             "PROVISIONAL — the least validated metric in COMPAS "
             "(Spearman 0.41 against one hand-written ordering of 19 "
             "tracks). Off by default; calibrate it on your own library "
             "before trusting it.",
    ),
    Axis(
        key="energy", name="Lift", value=lambda a: a.energy,
        thresholds=(4.0, 5.2),
        labels={ENGLISH: ("gentle", "moderate", "lively"),
                TANGO: ("suave", "medio", "enérgico")},
        neutral=1,
        help="From Energy (1-10): how much the track will move a floor.",
    ),
    Axis(
        key="dynamics", name="Dynamics", value=lambda a: a.lra,
        thresholds=(5.6, 8.6),
        labels={ENGLISH: ("even", "dynamic", "dramatic"),
                TANGO: ("parejo", "dinámico", "dramático")},
        neutral=1,
        help="Quiet-to-loud spread, from LRA. Reads low on noisy shellac "
             "transfers, so compare within a similar era.",
    ),
    Axis(
        key="mode", name="Mode",
        value=lambda a: 1.0 if a.key.endswith("m") else 0.0,
        thresholds=(0.5,),
        labels={ENGLISH: ("major", "minor"), TANGO: ("mayor", "menor")},
        neutral=None, categorical=True,
        help="Major or minor, from the estimated Key — so it inherits the "
             "key estimate's uncertainty on shellac transfers.",
    ),
)

AXES_BY_KEY = {a.key: a for a in AXES}
DEFAULT_AXIS_KEYS = tuple(a.key for a in AXES if a.default)


def axis_level(axis: Axis, analysis: Any) -> int | None:
    """Level index for this track, or None when the input is missing."""
    if analysis is None:
        return None
    try:
        value = axis.value(analysis)
    except (AttributeError, TypeError):
        return None
    if value is None:
        return None
    level = 0
    for cut in axis.thresholds:
        if value < cut:
            break
        level += 1
    return level


def axis_label(axis: Axis, analysis: Any, vocabulary: str = ENGLISH) -> str:
    level = axis_level(axis, analysis)
    if level is None:
        return ""
    names = axis.labels.get(vocabulary, axis.labels[ENGLISH])
    return names[min(level, len(names) - 1)]


def resolve_axes(keys) -> list[Axis]:
    """Axis objects for the given keys, in the canonical AXES order."""
    wanted = set(keys)
    return [a for a in AXES if a.key in wanted]


def label(
    analysis: Any,
    vocabulary: str = ENGLISH,
    axis_keys=DEFAULT_AXIS_KEYS,
    skip_neutral: bool = True,
) -> str:
    """Composed description, e.g. 'fast driving instrumental'."""
    if analysis is None:
        return ""
    words: list[str] = []
    fallback: list[str] = []
    for axis in resolve_axes(axis_keys):
        level = axis_level(axis, analysis)
        if level is None:
            continue
        names = axis.labels.get(vocabulary, axis.labels[ENGLISH])
        name = names[min(level, len(names) - 1)]
        fallback.append(name)
        if skip_neutral and axis.neutral is not None and level == axis.neutral:
            continue
        words.append(name)
    if not words:
        # Every selected axis came out neutral: say something rather than
        # nothing, using the axes' own middle terms.
        return " ".join(fallback[:2])
    return " ".join(words)
