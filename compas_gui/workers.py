"""Background analysis workers (QThreadPool)."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal


class WorkerSignals(QObject):
    started = Signal(int, int)        # generation, row
    done = Signal(int, int, object)   # generation, row, TrackAnalysis
    failed = Signal(int, int, str)    # generation, row, message


class ScanSignals(QObject):
    scanned = Signal(int, object)     # generation, list[Path]


class ScanTask(QRunnable):
    """Walk dropped paths for audio files, off the UI thread.

    rglob over a music library is slow enough to matter — and under OneDrive
    it can touch cloud placeholders — so doing it inline blocked the event
    loop past Windows' ~5 s ghosting threshold and the window went
    "(Not Responding)" on a big drop.
    """

    def __init__(self, generation: int, paths, collect, signals) -> None:
        super().__init__()
        self.generation = generation
        self.paths = paths
        self.collect = collect
        self.signals = signals

    def run(self) -> None:
        try:
            files = self.collect(self.paths)
        except Exception:  # noqa: BLE001 — an unreadable tree is not fatal
            files = []
        self.signals.scanned.emit(self.generation, files)


class AnalyzeTask(QRunnable):
    def __init__(self, generation: int, row: int, path: Path,
                 rhythm: str, signals: WorkerSignals,
                 fast: bool = False) -> None:
        super().__init__()
        self.generation = generation
        self.row = row
        self.path = path
        self.rhythm = rhythm
        self.fast = fast
        self.signals = signals

    def run(self) -> None:  # executes on a pool thread
        self.signals.started.emit(self.generation, self.row)
        try:
            from compas_core import analyze_file
            result = analyze_file(self.path, rhythm=self.rhythm,
                                  fast=self.fast)
        except Exception as exc:  # noqa: BLE001 — report to UI
            self.signals.failed.emit(
                self.generation, self.row, f"{type(exc).__name__}: {exc}")
            return
        self.signals.done.emit(self.generation, self.row, result)


def suggested_thread_count() -> int:
    # librosa/numba saturate cores per track; 2-4 parallel is the sweet spot.
    return max(1, min(4, (os.cpu_count() or 4) - 1))


class LibrosaWarmup(QRunnable):
    """Import the heavy scientific stack once, off the UI thread."""

    def run(self) -> None:
        try:
            import librosa  # noqa: F401
            import numpy as np
            import compas_core.analyze  # noqa: F401
            # Trigger numba JIT on a tiny signal so the first real track
            # doesn't pay compile time.
            y = np.zeros(22050, dtype=np.float32)
            librosa.onset.onset_strength(y=y, sr=22050)
        except Exception:
            pass  # analysis tasks will surface real errors
