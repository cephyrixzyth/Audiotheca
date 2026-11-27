# Audiotheca all-in-one — API + nginx UI (Unraid Add Container)
# Web UI / API 1.0.12 · Engine 10.0.0
# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13
ARG AUDIOTHECA_VERSION=1.0.12
ARG ENGINE_VERSION=10.0.0
FROM node:24-alpine AS ui-build

WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json* ./
RUN npm ci
COPY ui/ .
COPY docs/assets/ /app/docs/assets/

ARG VITE_DEFAULT_LIBRARY_ROOT=/library
ENV VITE_DEFAULT_LIBRARY_ROOT=${VITE_DEFAULT_LIBRARY_ROOT}
RUN npm run build

FROM python:${PYTHON_VERSION}-slim-bookworm

ARG AUDIOTHECA_VERSION=1.0.12
ARG ENGINE_VERSION=10.0.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx p7zip-full curl tini clamav gettext-base \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY audiotheca/ audiotheca/
COPY api/ api/
COPY *.py ./

COPY --from=ui-build /app/ui/dist /usr/share/nginx/html
COPY deploy/unraid/nginx-local.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/unraid/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
# Official nginx image layout is not used here; entrypoint runs envsubst into conf.d.

LABEL org.opencontainers.image.title="Audiotheca" \
    org.opencontainers.image.description="Audiotheca audio library scanner and organizer (web UI + API engine)" \
    org.opencontainers.image.source="https://github.com/cephyrixzyth/Audiotheca" \
    org.opencontainers.image.url="https://github.com/cephyrixzyth/Audiotheca" \
    org.opencontainers.image.version="${AUDIOTHECA_VERSION}" \
    audiotheca.engine.version="${ENGINE_VERSION}" \
    audiotheca.ui.version="${AUDIOTHECA_VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    AUDIOTHECA_HOME=/data \
    AUDIOTHECA_LIBRARY_ROOT=/library \
    AUDIOTHECA_LIBRARY_ROOTS=/library \
    AUDIOTHECA_NO_RELOAD=1 \
    AUDIOTHECA_API_HOST=0.0.0.0 \
    AUDIOTHECA_API_PORT=8787 \
    AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP=1

EXPOSE 80 8787

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD curl -f http://127.0.0.1/api/health && curl -sf http://127.0.0.1:8787/api/health

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
