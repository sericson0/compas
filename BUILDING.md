# Building COMPAS from source

Most people don't need this — the [Releases page](https://github.com/sericson0/compas/releases)
has ready-to-run builds for Windows and Apple Silicon Macs. Build from source
if you're on an Intel Mac or Linux, if you want to run modified code, or if you
just don't want to trust someone else's binary.

Two levels: run it from Python (quick, needs Python), or produce a standalone
app (slower, needs nothing at runtime).

---

## 1. Run from Python

Needs Python 3.11 or newer. Check with `python --version` — on macOS and Linux
it's often `python3`.

```bash
git clone https://github.com/sericson0/compas.git
cd compas

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e .
```

That pulls in numpy, scipy, librosa, soundfile, mutagen, pyloudnorm and
PySide6 — around 500 MB, and a few minutes on a cold pip cache.

```bash
compas-gui                         # the GUI
compas example_songs               # the CLI
```

If the `compas` / `compas-gui` commands aren't found, the venv isn't active;
`python -m compas_cli` and `python -m compas_gui.app` work regardless.

### Linux

No release build is published for Linux, but the source install works. PySide6
needs a few system libraries that minimal distros omit:

```bash
sudo apt install libgl1 libegl1 libxkbcommon-x11-0 libdbus-1-3   # Debian/Ubuntu
```

`soundfile` needs libsndfile (`sudo apt install libsndfile1`), and reading MP3s
needs a working `ffmpeg` on PATH.

---

## 2. Build the standalone app

This bundles Python and every dependency into a folder that runs on a machine
with no Python at all. It uses [PyInstaller](https://pyinstaller.org) and the
shared spec at [packaging/compas.spec](packaging/compas.spec).

Start from an activated venv with the project installed (step 1), then:

| Platform | Command | Output |
| --- | --- | --- |
| Windows | `packaging\build_windows.bat` | `dist\COMPAS\COMPAS.exe` |
| macOS | `bash packaging/build_macos.sh` | `dist/COMPAS.app` |
| Linux | `pyinstaller packaging/compas.spec --noconfirm` | `dist/COMPAS/COMPAS` |

Expect 2–5 minutes and roughly 400 MB of output.

**Ship the whole folder.** On Windows and Linux the result is a directory, not
a single file — `COMPAS.exe` will not run if you move it out of `dist\COMPAS\`.
Zip the directory to hand it to someone else. macOS is the exception: `.app` is
already a directory that Finder treats as one item.

### Checking a build works

The GUI has no console, so a frozen-stack failure would otherwise be silent.
The launcher has a self-test that analyzes one file and writes the result (or
the full traceback) to a text file:

```bat
dist\COMPAS\COMPAS.exe --selftest result.txt example_songs\some_track.flac
```

```bash
dist/COMPAS.app/Contents/MacOS/COMPAS --selftest result.txt example_songs/some_track.flac
```

`result.txt` starts with `OK` or `FAIL`.

### Cross-building doesn't work

PyInstaller freezes the interpreter it is running under, so each target needs
its own machine: no Mac app from Windows, no Windows exe from a Mac. If you
don't have the hardware, fork the repo and run the
[Release workflow](.github/workflows/release.yml) — GitHub's runners provide
both. See [RELEASING.md](RELEASING.md).

### Intel Macs

The published macOS build is Apple Silicon only, because `llvmlite` (pulled in
by numba, pulled in by librosa) has shipped arm64-only macOS wheels since 0.46.
An x86_64 build falls back to compiling LLVM from source, which is why there's
no CI job for it.

Locally on an Intel Mac you have two options: install Xcode's command line
tools and let it compile (slow but works), or pin the last version with x86_64
wheels before installing — `pip install "llvmlite<0.46" "numba<0.62"`, which
freezes that part of the stack but builds in minutes.

---

## 3. macOS: signing

A build made on your own Mac runs on your own Mac with no ceremony. The moment
it travels — email, USB stick, a download — macOS quarantines it and Gatekeeper
refuses to open it. Distributing a Mac app to other people means signing it
with an Apple Developer ID and having Apple notarize it.

That's a release concern rather than a build concern, so it lives in
[RELEASING.md § macOS signing](RELEASING.md#macos-signing-and-notarization).
