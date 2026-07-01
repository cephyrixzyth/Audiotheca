#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

export PYTHONUNBUFFERED=1

if [[ -z "${AUDIOTHECA_LIBRARY_ROOT:-}" ]]; then
  echo "Tip: export AUDIOTHECA_LIBRARY_ROOT=/path/to/library (see docs/TESTING.md)"
fi

echo "Starting API on http://127.0.0.1:8787 ..."
python3 -m api.server &
API_PID=$!

cleanup() {
  kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 2

echo "Starting web UI on http://127.0.0.1:5173 ..."
cd ui
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run dev -- --host 127.0.0.1
