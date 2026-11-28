#!/bin/sh
set -e

export AUDIOTHECA_HOME="${AUDIOTHECA_HOME:-/data}"
export AUDIOTHECA_LIBRARY_ROOT="${AUDIOTHECA_LIBRARY_ROOT:-/library}"
export AUDIOTHECA_LIBRARY_ROOTS="${AUDIOTHECA_LIBRARY_ROOTS:-${AUDIOTHECA_LIBRARY_ROOT}}"
export AUDIOTHECA_API_HOST="${AUDIOTHECA_API_HOST:-127.0.0.1}"
export AUDIOTHECA_API_PORT="${AUDIOTHECA_API_PORT:-8787}"
export AUDIOTHECA_NO_RELOAD="${AUDIOTHECA_NO_RELOAD:-1}"
export AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP="${AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP:-1}"
export AUDIOTHECA_PROXY_SECRET="${AUDIOTHECA_PROXY_SECRET:-}"
export PYTHONUNBUFFERED=1

if [ "${AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP}" = "1" ] && [ -z "${AUDIOTHECA_PROXY_SECRET}" ]; then
    echo "AUDIOTHECA_PROXY_SECRET is required when AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP=1" >&2
    exit 1
fi

# Render nginx config so the proxy secret can be injected without baking tokens into JS.
if [ -f /etc/nginx/templates/default.conf.template ]; then
    envsubst '${AUDIOTHECA_PROXY_SECRET}' \
        < /etc/nginx/templates/default.conf.template \
        > /etc/nginx/conf.d/default.conf
elif [ -f /etc/nginx/conf.d/default.conf.template ]; then
    envsubst '${AUDIOTHECA_PROXY_SECRET}' \
        < /etc/nginx/conf.d/default.conf.template \
        > /etc/nginx/conf.d/default.conf
fi

# Drop root for the API: files it creates or moves on the shares get PUID:PGID.
/usr/local/bin/run-as-user python -m api.server &
API_PID=$!

i=0
while [ "$i" -lt 60 ]; do
    if curl -sf "http://127.0.0.1:${AUDIOTHECA_API_PORT}/api/health" >/dev/null 2>&1; then
        break
    fi
    i=$((i + 1))
    sleep 1
done

nginx -g 'daemon off;' &
NGINX_PID=$!

term_handler() {
    kill -TERM "$NGINX_PID" "$API_PID" 2>/dev/null || true
    wait "$NGINX_PID" "$API_PID" 2>/dev/null || true
}

trap term_handler TERM INT

wait "$NGINX_PID"
term_handler
