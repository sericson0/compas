#!/usr/bin/env bash
# Build the macOS app bundle into dist/COMPAS.app.
# Run ON A MAC from anywhere:  bash packaging/build_macos.sh
# Needs Python 3.11+ with the project deps installed (pip install -e .).
#
# Optional, to sign the build for distribution:
#   export COMPAS_CODESIGN_IDENTITY="Developer ID Application: Name (TEAMID)"
# Unset, the build is unsigned — fine on this Mac, refused on any other.
# Notarization is a separate step; see RELEASING.md.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install --quiet pyinstaller
python3 -m PyInstaller packaging/compas.spec --noconfirm

echo
echo "Done: dist/COMPAS.app"
if [ -n "${COMPAS_CODESIGN_IDENTITY:-}" ]; then
  codesign --verify --deep --strict --verbose=2 dist/COMPAS.app
  echo "Signed with: $COMPAS_CODESIGN_IDENTITY"
  echo "To distribute it, notarize and staple — see RELEASING.md."
else
  echo "Unsigned. First launch on another Mac needs: right-click > Open,"
  echo "or:  xattr -dr com.apple.quarantine dist/COMPAS.app"
fi
