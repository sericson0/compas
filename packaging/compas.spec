# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the COMPAS GUI.

Build from the repo root (or anywhere — paths are spec-relative):

    pyinstaller packaging/compas.spec --noconfirm

Produces dist/COMPAS/ with COMPAS.exe on Windows, and additionally
dist/COMPAS.app on macOS.
"""

import os
import sys

ROOT = os.path.dirname(SPECPATH)  # noqa: F821 — SPECPATH is injected by PyInstaller

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

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="COMPAS",
    debug=False,
    strip=False,
    upx=False,
    console=False,
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
        bundle_identifier="org.compas.tango-analyzer",
        info_plist={
            "CFBundleName": "COMPAS",
            "CFBundleDisplayName": "COMPAS — Tango Music Analyzer",
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
        },
    )
