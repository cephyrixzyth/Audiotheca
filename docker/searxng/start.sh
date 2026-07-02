#!/usr/bin/env bash
# Start local SearXNG for Audiotheca research (Linux / macOS / WSL)
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not found. Install Docker Desktop or docker-ce, then re-run ./start.sh"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker engine not running. Start Docker Desktop / systemctl docker, then re-run."
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

docker compose up -d

echo ""
echo "Waiting for SearXNG..."
for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${SEARXNG_PORT:-8080}/healthz" >/dev/null 2>&1; then
    echo "SearXNG ready: http://127.0.0.1:${SEARXNG_PORT:-8080}"
    echo "Search: python ../../scripts/searx_search.py --preset vendor --arg \"Native Instruments\""
    exit 0
  fi
  sleep 2
done

echo "SearXNG started but health check timed out — try: docker compose logs core"
exit 1
