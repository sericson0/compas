"""Audio decoding: soundfile for FLAC/WAV/OGG, ffmpeg fallback for the rest."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

ANALYSIS_SR = 22050  # mono @ 22.05 kHz is plenty for beat/key/energy features

# libsndfile >= 1.1 decodes MP3, so the ffmpeg fallback is only needed for
# the MPEG-4 family (m4a/aac) and wma. Every ffmpeg call is a process spawn
# plus a full-file pipe, so keeping MP3 in-process is both faster and quieter.
_SOUNDFILE_EXTS = {".flac", ".wav", ".ogg", ".oga", ".aiff", ".aif", ".mp3"}


def load_audio(path: str | Path, sr: int = ANALYSIS_SR) -> tuple[np.ndarray, int]:
    """Load an audio file as mono float32 at the analysis sample rate."""
    path = Path(path)
    first_error: Exception | None = None
    if path.suffix.lower() in _SOUNDFILE_EXTS:
        try:
            return _load_soundfile(path, sr), sr
        except Exception as exc:  # noqa: BLE001 — ffmpeg may still manage it
            # Keep it: if ffmpeg also fails, a corrupt FLAC otherwise gets
            # reported as an ffmpeg problem, which sends you looking in
            # entirely the wrong place.
            first_error = exc
    return _load_ffmpeg(path, sr, first_error), sr


def _load_soundfile(path: Path, sr: int) -> np.ndarray:
    import soundfile as sf
    import librosa

    y, file_sr = sf.read(str(path), dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if file_sr != sr:
        y = librosa.resample(y, orig_sr=file_sr, target_sr=sr, res_type="soxr_hq")
    return np.ascontiguousarray(y, dtype=np.float32)


def _no_console_kwargs() -> dict:
    """Keep ffmpeg from flashing up a console window on Windows.

    The GUI runs windowed (pythonw.exe, or the packaged build), so it has no
    console of its own — without this flag Windows gives the child one, and
    a batch of m4a files pops a command prompt per track.
    """
    if sys.platform != "win32":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _load_ffmpeg(path: Path, sr: int,
                 first_error: Exception | None = None) -> np.ndarray:
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-ac", "1", "-ar", str(sr), "-f", "f32le", "-",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, check=False, **_no_console_kwargs())
    except FileNotFoundError as exc:
        # Raw, this surfaces in the GUI's Status column as "[WinError 2] The
        # system cannot find the file specified", which names neither ffmpeg
        # nor the track.
        raise RuntimeError(
            f"ffmpeg was not found on PATH, and it is needed to decode "
            f"{path.name}. Install ffmpeg, or convert the file to FLAC/WAV."
        ) from exc
    if proc.returncode != 0 or not proc.stdout:
        detail = proc.stderr.decode(errors="replace")[:400].strip()
        message = f"ffmpeg failed to decode {path.name}: {detail}"
        if first_error is not None:
            message += (f"\n(soundfile also failed first: "
                        f"{type(first_error).__name__}: {first_error})")
        raise RuntimeError(message) from first_error
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()
