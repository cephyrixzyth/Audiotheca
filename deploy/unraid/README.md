# Audiotheca on Unraid

Production Docker stack: **API** (FastAPI + scan engine) + **UI** (nginx + Vite build) + **SearXNG** (vendor research), with optional **ClamAV** / **VPN** profiles.

Designed for Unraid 6.x/7.x where the audio library lives on local array paths (`/mnt/user/...`), not over SMB from a PC.

Main project docs: [README](../../README.md) · Engine **10.0.0** · Web UI **1.0.12**

## Community Applications

Once listed, install from **Apps** → search **Audiotheca**. Template location and requirements: [COMMUNITY-APPS.md](COMMUNITY-APPS.md).

## Add Container (self-build)

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
# tags: audiotheca/unraid:latest and audiotheca/unraid:<version from tauri.conf.json>
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

For multi-container (API + UI + SearXNG), use Compose instead:
2. Copy this folder to e.g. `/mnt/user/appdata/audiotheca/compose/`.
3. Copy `.env.example` → `.env` and set `LIBRARY_HOST_PATH` to your **local** share path.
4. Create appdata: `mkdir -p /mnt/user/appdata/audiotheca`
5. Build and start:

```bash
cd /mnt/user/appdata/audiotheca/compose
docker compose up -d --build
```

6. Open `http://<unraid-ip>:4210` in a browser on your LAN. SearXNG is on `http://127.0.0.1:8081` on the Unraid host (localhost only).

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
| `api` | internal `:8787` | Not published to the host by default; UI nginx proxies `/api/` |
| `searxng` | 8081 (localhost) | Vendor research / WEB-SPDR — starts with the default stack |
| `clamav` | 3310 (localhost) | Optional — `docker compose --profile clamav up -d` |
| `gluetun` | shares API/SearXNG ports | Optional VPN sidecar — `docker compose --profile vpn up -d` |

## Optional profiles

**ClamAV** (Security tab deep scans):

```bash
docker compose --profile clamav up -d --build
```

**Gluetun VPN** (DKR-TUN — route outbound traffic through VPN; configure `.env` VPN vars):

```bash
AUDIOTHECA_API_UPSTREAM=gluetun:8787 docker compose --profile vpn up -d --build
docker compose stop api searxng
```

The UI proxy then reaches the VPN API through Gluetun. Keep the upstream override when recreating the UI. See **[SMOKE-VPN.md](SMOKE-VPN.md)** for wiring-only and live VPN smoke steps (no creds in repo).

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
- `AUDIOTHECA_API_TOKEN` — **required** fixed bearer (server-side / never in the JS bundle)
- `AUDIOTHECA_PROXY_SECRET` — **required** shared secret for opaque HttpOnly session minting via nginx
- `SEARXNG_URL` — in-compose URL for the API (`http://searxng:8080`); host UI is `127.0.0.1:${SEARXNG_PORT:-8081}`

## Security

- API binds `0.0.0.0` inside the Docker network only and is **not published** to the host by default.
- Expose the UI port to LAN (nginx proxies `/api/`). Do not publish API port `8787` unless debugging.
- Set strong `AUDIOTHECA_API_TOKEN` and `AUDIOTHECA_PROXY_SECRET` in `.env` (and in the Unraid Add Container template).
- The UI nginx injects the proxy secret so `/api/auth/session` can set an **opaque HttpOnly** cookie — the long-lived bearer is never baked into the JS bundle or stored in the cookie value.
- Token bootstrap (`GET /api/auth/token`) is disabled in the default compose (`AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP=1`).
- The API runs as `PUID:PGID` (default `99:100`, nobody:users) with `UMASK=000`, so staged, quarantined and moved files stay editable over SMB. Only the appdata folder is chowned at startup; the library is never touched. `PUID=0` restores root.
- In the all-in-one image the API binds `127.0.0.1` and port `8787` is no longer exposed; nginx is the only entry point.
- To gate quarantine, delete, shred and live execution, set `AUDIOTHECA_REQUIRE_ADMIN=1` and `AUDIOTHECA_ADMIN_TOKEN`; the Security panel asks for the admin token before those actions run.
- Desktop and dev installs reject requests whose `Host` is not loopback, an IP address or listed in `AUDIOTHECA_ALLOWED_HOSTS` (DNS-rebinding protection). The legacy `?token=` query credential is off unless `AUDIOTHECA_ALLOW_QUERY_TOKEN=1`.
- For reverse proxy (Nginx Proxy Manager / SWAG): proxy to `ui:80`, enable WebSocket upgrade for scan progress, and prefer proxy auth.

## Smoke test

```bash
# UI (includes proxied /api/)
curl -sf http://127.0.0.1:4210/ | head
# Direct bearer still works for scripting; the browser uses a session cookie instead.
curl -sf -H "Authorization: Bearer $AUDIOTHECA_API_TOKEN" \
  http://127.0.0.1:4210/api/security/library-roots | jq .
# Session via nginx proxy secret (opaque cookie — not the API token):
curl -sf -c - -X POST http://127.0.0.1:4210/api/auth/session | head
```

Start a dry-run scan from the **Scan** tab; progress streams over WebSocket at `/api/jobs/{id}/events?ticket=…`.

To debug the API on the host, temporarily add under the `api` service:

```yaml
ports:
  - "${API_PORT:-4211}:8787"
```

## Run tests in the API image

```bash
docker compose run --rm --no-deps api pytest tests/ -q
```

## Community Applications template

`my-audiotheca.xml` is a full Unraid **Add Container** template. Install with `install-template.sh` (see above) or copy manually to `/boot/config/plugins/dockerMan/templates-user/audiotheca.xml`.

## Windows Docker Desktop

Do not set `LIBRARY_HOST_PATH` to a mapped drive letter (`Z:/_software/_audio`). Docker parses `:` as a volume separator and errors with `invalid volume specification`.

Use a UNC path instead, and add that share under **Docker Desktop → Settings → Resources → File sharing**:

```
LIBRARY_HOST_PATH=//nas-host/share/_software/_audio
```

`.\start-local.ps1` converts `Z:/...` to UNC automatically. Extra Compose profiles (`vpn`, `space-recovery`) are not started unless you pass them yourself.

## Windows dev vs Unraid

| Layout | UI | API |
|--------|-----|-----|
| Windows + Tauri dev | Vite `:5173` | `:8787` localhost |
| Unraid Docker | nginx `:4210` | host `:4211` / internal `:8787` |

Both layouts share the same API and UI codebase; library root comes from env on Unraid and from `Z:\` defaults on Windows.
