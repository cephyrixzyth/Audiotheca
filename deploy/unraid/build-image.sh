#!/bin/bash
# Build the Audiotheca Unraid image (run from repo root or this directory).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

TAG="${1:-audiotheca/unraid:latest}"
VERSION_TAG="audiotheca/unraid:1.0.0"
echo "Building ${TAG} and ${VERSION_TAG} ..."
docker build -f deploy/unraid/Dockerfile \
  --build-arg AUDIOTHECA_VERSION=1.0.0 \
  --build-arg ENGINE_VERSION=10.0.0 \
  -t "$TAG" -t "$VERSION_TAG" .
echo "Done. Images: ${TAG}, ${VERSION_TAG}"
