#!/bin/bash
# Build the Audiotheca Unraid image (run from repo root or this directory).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

TAG="${1:-audiotheca/unraid:latest}"
echo "Building ${TAG} ..."
docker build -f deploy/unraid/Dockerfile -t "$TAG" .
echo "Done. Image: ${TAG}"
