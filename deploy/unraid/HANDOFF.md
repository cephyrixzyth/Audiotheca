# Audiotheca on Unraid — new chat handoff

Copy everything below the line into a **new Cursor chat** to build the full Docker package.

---

## Prompt for new chat

```
Build a production Docker stack for Audiotheca on Unraid 6.x/7.x.

## Goal
Single installable package (docker-compose + Dockerfiles + Unraid template notes) that runs on the Unraid box where the library disks live locally (not over SMB from a PC). Browser UI + API + engine scans should use fast local paths under /mnt/user/...

## Current project
Path: c:\Users\Cephyrix Zyth\Desktop\audiotheca
- Engine 10.0.0, UI 1.0.12, FastAPI `api/server.py` + `api/routers/`
- Library root (Windows/SMB today): Z:\_software\_audio
  Unraid equivalent (adjust to my share): likely /mnt/user/<pool>/_software/_audio
  SMB name seen in reports: \\192.168.50.116\infernal-data-streams\_software\_audio
- Reports/cache: dedupe_reports/ (AUDIOTHECA_HOME)
- Feedback: dedupe_reports/feedback/ (vendors, underscore whitelist, etc.)

## Services to containerize
1. **audiotheca-api** — python -m api.server (port 8787)
   - Env: AUDIOTHECA_HOME, AUDIOTHECA_API_PORT, AUDIOTHECA_LIBRARY_ROOTS
   - Mount: library read-only or rw as needed, AUDIOTHECA_HOME rw for reports
2. **audiotheca-ui** — nginx serving Vite build, proxy /api to api service
   - Or single container with API + static UI
3. **searxng** (optional sibling) — already stubbed in docker/searxng/

## Must-haves
- docker-compose.yml for Unraid (Community Applications → Compose plugin or manual)
- .env.example with UNRAID paths
- Dockerfile(s) multi-stage: Python 3.12+ deps, Node build for ui/
- ROOT_DIR / library root from env (config.py currently hardcodes Z:\ — add AUDIOTHECA_LIBRARY_ROOT)
- UI DEFAULT_LIBRARY_ROOT from build-time or runtime config endpoint
- Health checks, restart policies, log to stdout
- Document Unraid volume mappings:
  - /mnt/user/appdata/audiotheca → AUDIOTHECA_HOME (reports, cache, token)
  - /mnt/user/.../_software/_audio → library (local disk path on array)
- Security: API token, bind UI to LAN or reverse proxy (Nginx Proxy Manager / SWAG)

## Nice-to-haves
- Unraid XML template snippet for CA
- space_recovery.py as optional one-shot profile
- scripts/searx_search.py wired to searxng service on same compose network
- Watch scan progress via existing WebSocket /api/jobs/{id}/events

## Recent features to preserve
- Underscore vendor whitelist (dedupe_reports/feedback/underscore_whitelist.json)
- Space Recovery tab, flow editor, section reorder
- Full-library dry scan after whitelist (not target_paths-only)

## Testing
- pytest in API container or CI stage
- Smoke: curl /api/health, UI loads, dry-run job starts against mounted library path

Start from deploy/unraid/ skeleton in the repo and flesh out Dockerfiles + compose.
```

---

## Local Windows Docker (dev)

From `deploy/unraid/`:

```powershell
copy .env.example .env   # edit LIBRARY_HOST_PATH
.\start-local.ps1
# UI http://localhost:4210 · API http://localhost:4211/api/health
```

## What already exists in repo

| Path | Status |
|------|--------|
| `docker/searxng/` | SearXNG compose + JSON API settings (Windows dev) |
| `deploy/unraid/` | Compose stack + **Add Container** template (`my-audiotheca.xml`, `Dockerfile`) |
| `deploy/unraid/start-local.ps1` | Windows Docker Desktop local stack |
| `scripts/searx_search.py` | SearXNG CLI helper |
| `scripts/seed_demo_library.py` | Demo library under `docs/demo/library` |
| `audiotheca/spec/` | 94-code architecture spec catalog + invoke API |
| `docs/SPEC_CATALOG.md` | Spec catalog reference |
| `docs/TAURI_BUILD.md` | Sidecar pattern (reference for AUDIOTHECA_HOME) |

## Resolved (was gaps in early handoff)

1. `AUDIOTHECA_LIBRARY_ROOT` env — supported in config and API security
2. UI library root — from `/api/security/library-roots` at runtime
3. Dockerfiles — `deploy/unraid/Dockerfile`, `Dockerfile.api`, `Dockerfile.ui`
4. 7-Zip — bundled via `tools/7zip/` or system path in container
5. Spec waves A–R — 94/94 codes implemented with tests

## Suggested Unraid paths (user to confirm)

```bash
# Appdata (persistent)
/mnt/user/appdata/audiotheca          → /data          # AUDIOTHECA_HOME, dedupe_reports

# Library (local array — fast)
/mnt/user/infernal-data-streams/_software/_audio  → /library   # read-only for dry-run

# Optional: entire _software tree
/mnt/user/infernal-data-streams/_software → /software
```

## Network ports (LAN)

| Service | Port |
|---------|------|
| UI | 4210 (nginx) |
| API | 4211 (host) / 8787 (container) |
| SearXNG | 8080 (different host port, e.g. 8081) |

---

After the new chat finishes, retire Windows-only dev ports (8788/8790) or document both layouts.
