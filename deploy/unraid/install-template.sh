#!/bin/bash
# Install Audiotheca into Unraid Docker Manager user templates (run on Unraid).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_DIR="/boot/config/plugins/dockerMan/templates-user"
XML_DEST="${TEMPLATE_DIR}/audiotheca.xml"
ICON_DEST="${TEMPLATE_DIR}/audiotheca-icon.png"
ICON_SRC="${SCRIPT_DIR}/icon.png"

if [ ! -d "$TEMPLATE_DIR" ]; then
    echo "Unraid template directory not found: $TEMPLATE_DIR"
    echo "Run this script on your Unraid server."
    exit 1
fi

mkdir -p "$TEMPLATE_DIR"
cp "${SCRIPT_DIR}/my-audiotheca.xml" "$XML_DEST"

if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$ICON_DEST"
else
    echo "Warning: ${ICON_SRC} missing — template will use default icon."
fi

echo "Installed:"
echo "  $XML_DEST"
[ -f "$ICON_DEST" ] && echo "  $ICON_DEST"
echo ""
echo "Next: Docker tab → Add Container → Template: Audiotheca"
echo "      (build image first: bash ${SCRIPT_DIR}/build-image.sh)"
