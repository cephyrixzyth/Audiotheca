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
- Engine 10.0.0, UI 1.0.0, FastAPI api/server.py
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

## What already exists in repo

| Path | Status |
|------|--------|
| `docker/searxng/` | SearXNG compose + JSON API settings (Windows dev) |
| `deploy/unraid/` | Compose stack + **Add Container** template (`my-audiotheca.xml`, `Dockerfile`) |
| `scripts/searx_search.py` | SearXNG CLI helper |
| `docs/TAURI_BUILD.md` | Sidecar pattern (reference for AUDIOTHECA_HOME) |

## Known gaps for Unraid (new chat should fix)

1. `audiotheca/config.py` — `ROOT_DIR` hardcoded; needs `AUDIOTHECA_LIBRARY_ROOT` env
2. `ui/src/platform.ts` — `DEFAULT_LIBRARY_ROOT` hardcoded for Windows
3. No Dockerfile yet — greenfield
4. Engine may need `7z` in container for archive peek
5. Live restructure on Linux needs different “open in explorer” / path semantics (API already has security path allowlist via `AUDIOTHECA_LIBRARY_ROOTS`)

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
