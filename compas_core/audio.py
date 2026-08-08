"""Audio decoding: soundfile for FLAC/WAV/OGG, ffmpeg fallback for the rest."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

ANALYSIS_SR = 22050  # mono @ 22.05 kHz is plenty for beat/key/energy features

_SOUNDFILE_EXTS = {".flac", ".wav", ".ogg", ".oga", ".aiff", ".aif"}


def load_audio(path: str | Path, sr: int = ANALYSIS_SR) -> tuple[np.ndarray, int]:
    """Load an audio file as mono float32 at the analysis sample rate."""
    path = Path(path)
    if path.suffix.lower() in _SOUNDFILE_EXTS:
        try:
            return _load_soundfile(path, sr), sr
        except Exception:
            pass  # fall through to ffmpeg
    return _load_ffmpeg(path, sr), sr


def _load_soundfile(path: Path, sr: int) -> np.ndarray:
    import soundfile as sf
    import librosa

    y, file_sr = sf.read(str(path), dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if file_sr != sr:
        y = librosa.resample(y, orig_sr=file_sr, target_sr=sr, res_type="soxr_hq")
    return np.ascontiguousarray(y, dtype=np.float32)


def _load_ffmpeg(path: Path, sr: int) -> np.ndarray:
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-ac", "1", "-ar", str(sr), "-f", "f32le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(
            f"ffmpeg failed to decode {path.name}: {proc.stderr.decode(errors='replace')[:400]}"
        )
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()
