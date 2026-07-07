#!/usr/bin/env bash
set -euo pipefail

cd /work

if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  ln -sf "$(command -v python3)" /usr/local/bin/python
fi

pip3 install --break-system-packages -r requirements.txt pyinstaller

cd ui
npm ci
cd /work

export AUDIOTHECA_TARGET=x86_64-unknown-linux-gnu
export CARGO_TARGET_DIR=/work/ui/src-tauri/target

./scripts/build-installers.sh

echo ""
echo "Linux installers ready under dist/installers/linux/"