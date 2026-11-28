#!/bin/sh
# Run a command as the Unraid share owner instead of root.
#
# PUID / PGID default to 99 / 100 (nobody:users, Unraid's share owner) and
# UMASK to 000 so files Audiotheca moves, stages or writes stay editable over
# SMB. Set PUID=0 to keep the old root behaviour.
set -e

PUID="${PUID:-99}"
PGID="${PGID:-100}"
UMASK="${UMASK:-000}"

umask "$UMASK"

if [ "$(id -u)" != "0" ] || [ "$PUID" = "0" ]; then
    exec "$@"
fi

if ! getent group "$PGID" >/dev/null 2>&1; then
    groupadd -o -g "$PGID" audiotheca
fi
GROUP_NAME="$(getent group "$PGID" | cut -d: -f1)"

if ! getent passwd "$PUID" >/dev/null 2>&1; then
    useradd -o -u "$PUID" -g "$PGID" -M -d "${AUDIOTHECA_HOME:-/data}" -s /usr/sbin/nologin audiotheca
fi

# Appdata must be writable by the runtime user (reports, token, feedback,
# ledger). Only the appdata tree is chowned; the library is never touched.
DATA_DIR="${AUDIOTHECA_HOME:-/data}"
mkdir -p "$DATA_DIR"
if [ "$(stat -c '%u:%g' "$DATA_DIR")" != "$PUID:$PGID" ]; then
    chown -R "$PUID:$GROUP_NAME" "$DATA_DIR" 2>/dev/null || \
        echo "warning: could not chown $DATA_DIR to $PUID:$PGID" >&2
fi

exec gosu "$PUID:$PGID" "$@"
