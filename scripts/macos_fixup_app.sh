#!/usr/bin/env bash
# Clear Gatekeeper quarantine and ad-hoc re-sign Audiotheca after drag-install from DMG.
# Usage: ./scripts/macos_fixup_app.sh [/Applications/Audiotheca.app]

set -euo pipefail

APP="${1:-/Applications/Audiotheca.app}"

if [[ ! -d "$APP" ]]; then
  echo "App bundle not found: $APP" >&2
  echo "Drag Audiotheca from the DMG into Applications first." >&2
  exit 1
fi

echo "Removing quarantine from $APP ..."
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

echo "Ad-hoc signing embedded binaries ..."
while IFS= read -r -d '' bin; do
  codesign --force --sign - "$bin" 2>/dev/null || true
done < <(find "$APP/Contents/MacOS" "$APP/Contents/Resources" -type f -perm +111 -print0 2>/dev/null || true)

echo "Ad-hoc signing app bundle ..."
codesign --force --deep --sign - "$APP"

echo "Done. Open Audiotheca from Applications (or right-click → Open once)."
echo "If the window still does not appear, check:"
echo "  ~/Library/Application Support/com.audiotheca.desktop/audiotheca-desktop.log"
