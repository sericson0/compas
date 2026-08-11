"""Facet grid: continuous metrics turned into words.

Each axis is one thresholded number that COMPAS already reports, rendered
in one of two vocabularies:

    english   fast / driving / staccato / steady / instrumental
    tango     rapido / ritmico / picado / compas / instrumental

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
Provisional. Every cut point below was placed to split the 19-track
example corpus into sensible groups, which is enough to make the feature
usable and nowhere near enough to make it right. Run
``scripts/calibrate_facets.py`` over a real library to replace them with
percentiles of an actual tango collection.
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


def _tempo_rel(a: Any) -> float | None:
    try:
        spec = RHYTHM_SPECS[Rhythm(a.rhythm)]
    except (ValueError, KeyError):
        return None
    return a.bpm / spec.bpm_typical


def _vocal_level(a: Any) -> float | None:
    return {"instrumental": 0.0, "estribillo": 1.0,
            "vocal": 2.0}.get(a.vocal)


AXES: tuple[Axis, ...] = (
    Axis(
        key="tempo", name="Tempo", value=_tempo_rel,
        thresholds=(0.98, 1.05),
        labels={ENGLISH: ("slow", "medium", "fast"),
                TANGO: ("lento", "medio", "rapido")},
        neutral=1, default=True,
        help="Tempo relative to what is typical for this rhythm, so a vals "
             "at 210 BPM is not automatically 'fast'. BPM divided by the "
             "genre's typical tempo; cuts at 0.98 and 1.05.",
    ),
    Axis(
        key="drive", name="Character", value=lambda a: a.drive,
        thresholds=(30.0, 60.0),
        labels={ENGLISH: ("smooth", "balanced", "driving"),
                TANGO: ("melodico", "mixto", "ritmico")},
        neutral=1, default=True,
        help="The classic tango axis, from Drive: how hard the compas is "
             "marked. Melodico below 30, ritmico from 60.",
    ),
    Axis(
        key="articulation", name="Articulation",
        value=lambda a: a.articulation,
        thresholds=(25.0, 55.0),
        labels={ENGLISH: ("legato", "detached", "staccato"),
                TANGO: ("ligado", "medio", "picado")},
        neutral=1,
        help="How notes are attacked and released, from Articulation. "
             "Independent of Character: an orchestra can mark the compas "
             "hard with soft attacks, or play lightly with crisp ones.",
    ),
    Axis(
        key="texture", name="Texture", value=lambda a: a.percussiveness,
        thresholds=(35.0, 65.0),
        labels={ENGLISH: ("sustained", "mixed", "percussive"),
                TANGO: ("lirico", "equilibrado", "percusivo")},
        neutral=1,
        help="Melodic/sustained versus percussive, from Texture "
             "(spectrogram anisotropy). Bowed strings and held bandoneon "
             "chords sit low; piano and staccato marking sit high.",
    ),
    Axis(
        key="syncopation", name="Placement", value=lambda a: a.syncopation,
        thresholds=(35.0, 55.0),
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
                TANGO: ("compas", "fraseo")},
        neutral=0, default=True,
        help="From Timing: steady enough to dance without surprises, or "
             "noticeable rubato. Steady is the unmarked case, so it is "
             "left out of the composed label.",
    ),
    Axis(
        key="vocal", name="Voice", value=_vocal_level,
        thresholds=(0.5, 1.5),
        labels={ENGLISH: ("instrumental", "refrain", "vocal"),
                TANGO: ("instrumental", "estribillo", "cantado")},
        neutral=None, default=True,
        help="Instrumental, a refrain (estribillo), or sung throughout. "
             "Taken from the filename when it says 'instrumental', "
             "otherwise estimated from the audio.",
    ),
    Axis(
        key="harmony", name="Harmony", value=lambda a: a.harmonic_variety,
        thresholds=(45.0, 80.0),
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
        thresholds=(4.5, 6.0),
        labels={ENGLISH: ("gentle", "moderate", "lively"),
                TANGO: ("suave", "medio", "energico")},
        neutral=1,
        help="From Energy (1-10): how much the track will move a floor.",
    ),
    Axis(
        key="dynamics", name="Dynamics", value=lambda a: a.lra,
        thresholds=(6.0, 9.0),
        labels={ENGLISH: ("even", "dynamic", "dramatic"),
                TANGO: ("parejo", "dinamico", "dramatico")},
        neutral=1,
        help="Quiet-to-loud spread, from LRA. Reads low on noisy shellac "
             "transfers, so compare within a similar era.",
    ),
    Axis(
        key="mode", name="Mode",
        value=lambda a: 1.0 if a.key.endswith("m") else 0.0,
        thresholds=(0.5,),
        labels={ENGLISH: ("major", "minor"), TANGO: ("mayor", "menor")},
        neutral=None,
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
        name = axis.labels.get(vocabulary, axis.labels[ENGLISH])[
            min(level, len(axis.labels[ENGLISH]) - 1)]
        fallback.append(name)
        if skip_neutral and axis.neutral is not None and level == axis.neutral:
            continue
        words.append(name)
    if not words:
        # Every selected axis came out neutral: say something rather than
        # nothing, using the axes' own middle terms.
        return " ".join(fallback[:2])
    return " ".join(words)
