"""PyInstaller entry point for the COMPAS GUI."""

import sys


def _selftest(out_path: str, audio_path: str) -> int:
    """Analyze one file and write the result to out_path — verifies the
    frozen librosa/numba stack without a console (COMPAS.exe is windowed).

    Usage:  COMPAS.exe --selftest result.txt song.flac
    """
    from pathlib import Path
    try:
        from compas_core import analyze_file
        result = analyze_file(Path(audio_path))
        Path(out_path).write_text(
            "OK " + repr(result.to_dict()), encoding="utf-8")
        return 0
    except Exception as exc:  # noqa: BLE001 — report everything
        import traceback
        Path(out_path).write_text(
            f"FAIL {type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            encoding="utf-8")
        return 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        sys.exit(_selftest(sys.argv[i + 1], sys.argv[i + 2]))
    from compas_gui.app import main
    sys.exit(main())
