#!/bin/bash
# Build the Audiotheca Unraid image (run from repo root or this directory).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

UI_VERSION="$(bash "$ROOT/scripts/read-tauri-version.sh")"
TAG="${1:-audiotheca/unraid:latest}"
VERSION_TAG="audiotheca/unraid:${UI_VERSION}"
echo "Building ${TAG} and ${VERSION_TAG} (UI ${UI_VERSION}) ..."
docker build -f deploy/unraid/Dockerfile \
  --build-arg AUDIOTHECA_VERSION="${UI_VERSION}" \
  --build-arg ENGINE_VERSION=10.0.0 \
  -t "$TAG" -t "$VERSION_TAG" .
echo "Done. Images: ${TAG}, ${VERSION_TAG}"
