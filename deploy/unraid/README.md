# Audiotheca on Unraid

Production Docker stack: **API** (FastAPI + scan engine) + **UI** (nginx + Vite build), with optional **SearXNG** for vendor research.

Designed for Unraid 6.x/7.x where the audio library lives on local array paths (`/mnt/user/...`), not over SMB from a PC.

Main project docs: [README](../../README.md) · Engine **10.0.0** · Web UI **1.0.0**

## Add Container (recommended)

Unraid **Docker → Add Container** needs a single image and a user template.

### 1. Copy the repo to Unraid

```bash
# Example: clone or copy to appdata
cd /mnt/user/appdata
git clone <your-repo-url> audiotheca-src
# or: cp -r /path/from/PC/audiotheca /mnt/user/appdata/audiotheca-src
```

### 2. Build the image

```bash
cd /mnt/user/appdata/audiotheca-src
bash deploy/unraid/build-image.sh
# tags: audiotheca/unraid:latest
```

### 3. Install the Docker template

```bash
bash deploy/unraid/install-template.sh
```

This copies `my-audiotheca.xml` → `/boot/config/plugins/dockerMan/templates-user/audiotheca.xml` and the icon.

### 4. Add the container in the UI

1. **Docker** tab → **Add Container**
2. Template dropdown → **Audiotheca**
3. Confirm paths:
   - **Appdata** → `/mnt/user/appdata/audiotheca`
   - **Library** → `/mnt/user/infernal-data-streams/_software/_audio` (your local array path)
4. Ports: **WebUI** `4210`, **API** `4211` (optional)
5. **Apply**

Open `http://<unraid-ip>:4210`.

The all-in-one image runs nginx (UI) and the FastAPI engine in one container (`deploy/unraid/Dockerfile`).

## Docker Compose (optional)

For multi-container or SearXNG profiles, use Compose instead:
2. Copy this folder to e.g. `/mnt/user/appdata/audiotheca/compose/`.
3. Copy `.env.example` → `.env` and set `LIBRARY_HOST_PATH` to your **local** share path.
4. Create appdata: `mkdir -p /mnt/user/appdata/audiotheca`
5. Build and start:

```bash
cd /mnt/user/appdata/audiotheca/compose
docker compose up -d --build
```

6. Open `http://<unraid-ip>:4210` in a browser on your LAN.

## Volume mappings

| Host (Unraid) | Container | Purpose |
|---------------|-----------|---------|
| `/mnt/user/appdata/audiotheca` | `/data` | `AUDIOTHECA_HOME` — reports, scan cache, API token, feedback JSON |
| `/mnt/user/.../_software/_audio` | `/library` | Audio library (read-only mount for dry-run scans) |

The API reads `AUDIOTHECA_LIBRARY_ROOTS=/library` inside the container. The UI picks up the same path from `/api/security/library-roots`.

## Services

| Service | Port | Notes |
|---------|------|-------|
| `ui` | 4210 (default) | Browser entry point; proxies `/api` to the API container |
| `api` | 4211 | Direct API access (optional; UI proxy is usually enough) |
| `searxng` | 8081 (localhost) | Optional — `docker compose --profile search up -d` |

## Optional profiles

**SearXNG** (vendor/web research from the API network):

```bash
docker compose --profile search up -d --build
```

**Space recovery** (one-shot hardlink/bloat report):

```bash
docker compose --profile space-recovery run --rm space-recovery
```

Reports land under appdata: `/mnt/user/appdata/audiotheca/dedupe_reports/`.

## Environment

See `.env.example`. Key variables:

- `LIBRARY_HOST_PATH` — your array path (e.g. `/mnt/user/infernal-data-streams/_software/_audio`)
- `LIBRARY_CONTAINER_PATH` — leave as `/library` unless you change volume targets
- `APPDATA_PATH` — persistent config and reports
- `AUDIOTHECA_API_TOKEN` — optional fixed token; otherwise auto-written to appdata on first start

## Security

- API binds `0.0.0.0` inside the Docker network only; expose UI port to LAN, not API, when possible.
- Token bootstrap trusts the UI nginx container on the internal Docker network.
- For reverse proxy (Nginx Proxy Manager / SWAG): proxy to `ui:80`, enable WebSocket upgrade for scan progress.
- Set `AUDIOTHECA_API_TOKEN` in `.env` for a stable token across rebuilds.

## Smoke test

```bash
curl -sf http://127.0.0.1:4211/api/health | jq .
curl -sf http://127.0.0.1:4210/ | head
curl -sf http://127.0.0.1:4210/api/security/library-roots | jq .
```

Start a dry-run scan from the **Scan** tab; progress streams over WebSocket at `/api/jobs/{id}/events`.

## Run tests in the API image

```bash
docker compose run --rm --no-deps api pytest tests/ -q
```

## Community Applications template

`my-audiotheca.xml` is a full Unraid **Add Container** template. Install with `install-template.sh` (see above) or copy manually to `/boot/config/plugins/dockerMan/templates-user/audiotheca.xml`.

## Windows dev vs Unraid

| Layout | UI | API |
|--------|-----|-----|
| Windows + Tauri dev | Vite `:5173` | `:8787` localhost |
| Unraid Docker | nginx `:4210` | host `:4211` / internal `:8787` |

Both layouts share the same API and UI codebase; library root comes from env on Unraid and from `Z:\` defaults on Windows.
