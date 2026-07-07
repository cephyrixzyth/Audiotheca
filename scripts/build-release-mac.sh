#!/usr/bin/env bash
# Build macOS .dmg installers locally (Intel + Apple Silicon on Apple Silicon Mac).
# Outputs: dist/installers/mac/
#
# Usage (on macOS):
#   ./scripts/build-release-mac.sh            # native arch only (M-series -> arm64)
#   ./scripts/build-release-mac.sh --both     # arm64 + x86_64 (needs Rosetta on Apple Silicon)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS DMG builds must run on a Mac. Copy this repo to your M-series Mac and run:" >&2
  echo "  git pull && ./scripts/build-release-mac.sh --both" >&2
  exit 1
fi

BOTH=0
if [[ "${1:-}" == "--both" ]]; then
  BOTH=1
fi

copy_dmgs() {
  local triple="$1"
  local bundle=""
  for candidate in \
    "$ROOT/ui/src-tauri/target/$triple/release/bundle/dmg" \
    "$ROOT/ui/src-tauri/target/release/bundle/dmg"; do
    if [[ -d "$candidate" ]]; then
      bundle="$candidate"
      break
    fi
  done
  if [[ -z "$bundle" ]]; then
    echo "Warning: no dmg bundle for $triple" >&2
    return 1
  fi
  mkdir -p "$ROOT/dist/installers/mac"
  find "$bundle" -maxdepth 1 -type f -name '*.dmg' -exec cp -f {} "$ROOT/dist/installers/mac/" \;
}

build_target() {
  local triple="$1"
  local arch="${2:-}"
  echo ""
  echo "=== Building macOS sidecars + Tauri for $triple ==="
  export AUDIOTHECA_TARGET="$triple"
  export AUDIOTHECA_SIDECAR_ARCH="$arch"
  export CARGO_TARGET_DIR="$ROOT/ui/src-tauri/target"

  if [[ -n "$arch" ]] && [[ "$(uname -m)" == "arm64" ]] && [[ "$arch" == "x86_64" ]]; then
    arch -x86_64 python3 scripts/build_sidecars.py
    (cd ui && npm run sidecars && npx tauri build --target "$triple")
  else
    python3 scripts/build_sidecars.py
    (cd ui && npm run sidecars && npx tauri build --target "$triple")
  fi
  chmod +x "$ROOT/ui/src-tauri/binaries/"*-apple-darwin 2>/dev/null || true
  copy_dmgs "$triple"
}

pip3 install --upgrade pip >/dev/null
pip3 install -r requirements.txt pyinstaller >/dev/null

cd "$ROOT/ui"
if [[ ! -d node_modules ]]; then
  npm ci
fi
cd "$ROOT"

HOST="$(uname -m)"
if [[ "$BOTH" -eq 1 ]]; then
  build_target "aarch64-apple-darwin" "arm64"
  if ! xcode-select -p >/dev/null 2>&1; then
    echo "Warning: Xcode CLI tools recommended for x86_64 cross-build" >&2
  fi
  if [[ "$HOST" == "arm64" ]]; then
    if ! /usr/bin/pgrep -q oahd 2>/dev/null && ! arch -x86_64 true 2>/dev/null; then
      echo "Installing Rosetta for Intel DMG build ..."
      softwareupdate --install-rosetta --agree-to-license || true
    fi
  fi
  build_target "x86_64-apple-darwin" "x86_64"
elif [[ "$HOST" == "arm64" ]]; then
  build_target "aarch64-apple-darwin" "arm64"
else
  build_target "x86_64-apple-darwin" "x86_64"
fi

# Ad-hoc sign DMGs' app bundles are inside dmg; sign loose binaries if present
if command -v codesign >/dev/null 2>&1; then
  find "$ROOT/ui/src-tauri/binaries" -name '*-apple-darwin' -type f 2>/dev/null | while read -r bin; do
    chmod +x "$bin" || true
    codesign --force --sign - "$bin" 2>/dev/null || true
  done
fi

echo ""
echo "Done. macOS installers:"
ls -la "$ROOT/dist/installers/mac/" 2>/dev/null || echo "(no dmg copied - check target/release/bundle/dmg)"
