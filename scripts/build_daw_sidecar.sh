#!/usr/bin/env bash
# Build AudiothecaSidecar VST3/AU from exported blueprint directory.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)/plugins/daw_side/template"
if [[ -n "${1:-}" ]]; then ROOT="$1"; fi
mkdir -p "$ROOT/build"
cmake -S "$ROOT" -B "$ROOT/build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$ROOT/build" --config Release
echo "Done — see $ROOT/build/AudiothecaSidecar_artefacts/"
