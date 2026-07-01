#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "Audiotheca API starting on http://127.0.0.1:8787"
if [[ -n "${AUDIOTHECA_LIBRARY_ROOT:-}" ]]; then
  echo "Library root: $AUDIOTHECA_LIBRARY_ROOT"
else
  echo "Tip: export AUDIOTHECA_LIBRARY_ROOT=/path/to/library (see docs/TESTING.md)"
fi
echo "Health check: http://127.0.0.1:8787/api/health"
echo "List runs:    http://127.0.0.1:8787/api/runs"
echo ""
echo "Install Node.js to use the full web UI (see start-ui.sh)"
echo "Press Ctrl+C to stop."
echo ""

exec python3 -m api.server
