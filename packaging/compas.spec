# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the COMPAS GUI.

Build from the repo root (or anywhere — paths are spec-relative):

    pyinstaller packaging/compas.spec --noconfirm

Produces dist/COMPAS/ with COMPAS.exe on Windows, and additionally
dist/COMPAS.app on macOS.

Two environment variables tune the build; both are optional and both are set
by .github/workflows/release.yml:

    COMPAS_VERSION             version string baked into the macOS Info.plist
    COMPAS_CODESIGN_IDENTITY   Developer ID to sign the macOS build with

With no identity set, PyInstaller leaves its default ad-hoc signature, which
is enough to run locally on Apple Silicon but not enough to notarize.
"""

import os
import sys

ROOT = os.path.dirname(SPECPATH)  # noqa: F821 — SPECPATH is injected by PyInstaller

VERSION = os.environ.get("COMPAS_VERSION") or "0.1.0"

# Entitlements only matter when we are really signing — passing them with an
# ad-hoc signature just makes codesign noisier for no gain.
CODESIGN_IDENTITY = os.environ.get("COMPAS_CODESIGN_IDENTITY") or None
ENTITLEMENTS = (
    os.path.join(SPECPATH, "entitlements.plist")  # noqa: F821
    if CODESIGN_IDENTITY
    else None
)

a = Analysis(
    [os.path.join(SPECPATH, "compas_launcher.py")],  # noqa: F821
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # Big optional stacks librosa/scipy can drag in but COMPAS never uses.
    excludes=["matplotlib", "tkinter", "IPython", "PIL", "pandas", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

# The signing settings have to go on EXE and nowhere else. PyInstaller
# propagates them EXE -> COLLECT -> BUNDLE by copying attributes off the
# object it is handed; BUNDLE accepts codesign_identity as a keyword but
# overwrites it from its COLLECT argument, so setting it there looks right and
# does nothing.
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="COMPAS",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    codesign_identity=CODESIGN_IDENTITY,
    entitlements_file=ENTITLEMENTS,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="COMPAS",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="COMPAS.app",
        icon=None,
        version=VERSION,
        bundle_identifier="org.compas.tango-analyzer",
        # No codesign_identity here on purpose — it is inherited from `coll`,
        # which inherited it from `exe`. See the note above EXE.
        info_plist={
            "CFBundleName": "COMPAS",
            "CFBundleDisplayName": "COMPAS — Tango Music Analyzer",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            # COMPAS reads a music library and writes tags back into it, so it
            # will trip TCC the moment a user points it at ~/Music or an
            # external drive. Without these strings macOS denies the read
            # outright instead of showing a prompt.
            "NSDesktopFolderUsageDescription":
                "COMPAS needs access to analyze audio files you select.",
            "NSDocumentsFolderUsageDescription":
                "COMPAS needs access to analyze audio files you select.",
            "NSDownloadsFolderUsageDescription":
                "COMPAS needs access to analyze audio files you select.",
            "NSRemovableVolumesUsageDescription":
                "COMPAS needs access to analyze audio files on external drives.",
        },
    )
