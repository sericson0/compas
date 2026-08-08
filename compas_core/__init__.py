"""COMPAS — musical feature analysis for Argentine tango (tango / vals / milonga).

Core analysis library shared by the GUI, the CLI, and (later) the VST3 plugin
bridge. Public entry point: :func:`compas_core.analyze.analyze_file`.
"""

__version__ = "0.1.0"

from compas_core.rhythm import Rhythm, RhythmSpec, RHYTHM_SPECS
from compas_core.analyze import TrackAnalysis, analyze_file

__all__ = [
    "Rhythm",
    "RhythmSpec",
    "RHYTHM_SPECS",
    "TrackAnalysis",
    "analyze_file",
    "__version__",
]
