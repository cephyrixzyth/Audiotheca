#!/usr/bin/env bash
# Build Tauri installers for macOS (dmg) or Linux (AppImage + deb).
# Outputs: dist/installers/mac/ or dist/installers/linux/
# Requires: Rust, Node.js 24+, Python 3.11+ (sidecar build). No CLI needed for end users.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js/npm not found. Install from https://nodejs.org/" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "Python not found. Install Python 3.11+ for sidecar builds." >&2
  exit 1
fi

if ! command -v cargo >/dev/null 2>&1; then
  echo "Rust/cargo not found. Install from https://rustup.rs/" >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin)
    PLATFORM="mac"
    EXPECT=("dmg")
    ;;
  Linux)
    PLATFORM="linux"
    EXPECT=("appimage" "deb")
    ;;
  *)
    echo "Unsupported platform for build-installers.sh: $(uname -s)" >&2
    exit 1
    ;;
esac

OUT_DIR="$ROOT/dist/installers/$PLATFORM"
BUNDLE_DIR="$ROOT/ui/src-tauri/target/release/bundle"

echo "Building Audiotheca $PLATFORM installers (v1.0.0)..."

cd "$ROOT/ui"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run tauri:build

if [[ ! -d "$BUNDLE_DIR" ]]; then
  echo "Bundle directory not found: $BUNDLE_DIR" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
COPIED=0

for sub in "${EXPECT[@]}"; do
  src="$BUNDLE_DIR/$sub"
  if [[ ! -d "$src" ]]; then
    echo "Warning: missing bundle subfolder: $src" >&2
    continue
  fi
  while IFS= read -r -d '' file; do
    cp -f "$file" "$OUT_DIR/"
    echo "  -> $(basename "$file")"
    COPIED=$((COPIED + 1))
  done < <(find "$src" -maxdepth 1 -type f -print0)
done

if [[ "$COPIED" -eq 0 ]]; then
  echo "No installer artifacts copied. Check ui/src-tauri/target/release/bundle/" >&2
  exit 1
fi

echo ""
echo "Done. Installers in: $OUT_DIR"
ls -la "$OUT_DIR"
