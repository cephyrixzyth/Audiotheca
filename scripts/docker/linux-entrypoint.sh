#!/usr/bin/env bash
set -euo pipefail

cd /work

python3 -m pip install --break-system-packages --upgrade pip
pip3 install --break-system-packages -r requirements.txt pyinstaller

cd ui
if [[ ! -d node_modules ]]; then
  npm ci
fi
cd /work

export AUDIOTHECA_TARGET=x86_64-unknown-linux-gnu
export CARGO_TARGET_DIR=/work/ui/src-tauri/target

./scripts/build-installers.sh

echo ""
echo "Linux installers ready under dist/installers/linux/"
