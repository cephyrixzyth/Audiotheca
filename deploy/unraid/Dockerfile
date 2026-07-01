# Audiotheca all-in-one — API + nginx UI (Unraid Add Container)
# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13
FROM node:20-alpine AS ui-build

WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json* ./
RUN npm ci
COPY ui/ .

ARG VITE_DEFAULT_LIBRARY_ROOT=/library
ENV VITE_DEFAULT_LIBRARY_ROOT=${VITE_DEFAULT_LIBRARY_ROOT}
RUN npm run build

FROM python:${PYTHON_VERSION}-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx p7zip-full curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY audiotheca/ audiotheca/
COPY api/ api/
COPY *.py ./

COPY --from=ui-build /app/ui/dist /usr/share/nginx/html
COPY deploy/unraid/nginx-local.conf /etc/nginx/conf.d/default.conf
COPY deploy/unraid/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    AUDIOTHECA_HOME=/data \
    AUDIOTHECA_LIBRARY_ROOT=/library \
    AUDIOTHECA_LIBRARY_ROOTS=/library \
    AUDIOTHECA_NO_RELOAD=1 \
    AUDIOTHECA_API_HOST=0.0.0.0 \
    AUDIOTHECA_API_PORT=8787

EXPOSE 80 8787

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
    CMD curl -f http://127.0.0.1/api/health && curl -sf http://127.0.0.1:8787/api/health

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
