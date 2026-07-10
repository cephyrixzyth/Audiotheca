#!/usr/bin/env bash
# Read desktop shell version from ui/src-tauri/tauri.conf.json
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONF="${ROOT}/ui/src-tauri/tauri.conf.json"

if [[ ! -f "$CONF" ]]; then
  echo "Missing tauri.conf.json: $CONF" >&2
  exit 1
fi

python3 -c "import json, sys; print(json.load(open(sys.argv[1]))['version'])" "$CONF"
