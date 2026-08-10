#!/usr/bin/env bash
# Build the macOS app bundle into dist/COMPAS.app.
# Run ON A MAC from anywhere:  bash packaging/build_macos.sh
# Needs Python 3.11+ with the project deps installed (pip install -e .).
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --quiet pyinstaller
python3 -m PyInstaller packaging/compas.spec --noconfirm

echo
echo "Done: dist/COMPAS.app"
echo "First launch on another Mac may need: right-click > Open (unsigned app),"
echo "or remove the quarantine flag:  xattr -dr com.apple.quarantine dist/COMPAS.app"
