# Audiotheca — Configuration Reference

Engine **10.0.0** · API **1.0.12**

Overview and env quick-start: [main README](../README.md).

---

## Environment variables

Copy [.env.example](../.env.example) to `.env` for local overrides (load manually in PowerShell or use your shell's dotenv habit).

### Library & data paths

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIOTHECA_LIBRARY_ROOT` | `Z:\_software\_audio` | Primary library root for engine and scans |
| `AUDIOTHECA_LIBRARY_ROOTS` | same as above | Comma-separated allowlist for API path validation (scans, explorer, rescans) |
| `AUDIOTHECA_HOME` | *(repo root)* | Workspace for `dedupe_reports/`, cache, token, feedback |

Example:

```powershell
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\Libraries\_audio"
$env:AUDIOTHECA_LIBRARY_ROOTS = "D:\Libraries\_audio,D:\Libraries\_software"
$env:AUDIOTHECA_HOME = "C:\AudiothecaData"
```

Alternative allowlist file: `dedupe_reports/.library_roots.json` (see API security module).

### API server

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIOTHECA_API_PORT` | `8787` | HTTP port |
| `AUDIOTHECA_API_HOST` | `127.0.0.1` | Bind address — keep localhost unless you know what you are doing |
| `AUDIOTHECA_API_TOKEN` | *(auto)* | Fixed bearer token; else written to `dedupe_reports/.api_token` |
| `AUDIOTHECA_PROXY_SECRET` | *(unset)* | Shared secret between UI nginx and API for `POST /api/auth/session` (required for Docker/LAN when bootstrap is disabled) |
| `AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP` | unset | Set `1` to disable unauthenticated `GET /api/auth/token` (Docker/LAN default) |
| `AUDIOTHECA_TICKET_TTL_S` | `300` | Short-lived access ticket lifetime (30–3600 s) for WebSocket/media/download URLs |
| `AUDIOTHECA_SESSION_TTL_S` | `2592000` | Opaque session cookie lifetime in seconds (default 30 days) |
| `AUDIOTHECA_NO_RELOAD` | unset | Set `1` to disable uvicorn reload in dev |
| `AUDIOTHECA_ALLOW_REMOTE_TOKEN_BOOTSTRAP` | unset | Opt-in: allow token bootstrap from non-localhost (do not enable on LAN) |
| `AUDIOTHECA_TRUST_INTERNAL_NETWORK` | unset | Opt-in: treat private-network clients like trusted bootstrap peers |

### UI (Vite dev server)

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_PORT` | `8787` | Proxy target for `/api` in `npm run dev` |
| `VITE_DEFAULT_LIBRARY_ROOT` | `Z:\_software\_audio` | Build-time fallback; UI prefers `/api/security/library-roots` when API is up |

### Engine job runner (set by API, not usually manually)

| Variable | Description |
|----------|-------------|
| `AUDIOTHECA_PROGRESS_FILE` | JSONL progress events for WebSocket |
| `AUDIOTHECA_CONTROL_FILE` | Pause/stop/continue control |
| `AUDIOTHECA_SCAN_OPTIONS` | JSON scan options (skip phases, target paths, etc.) |
| `AUDIOTHECA_ENGINE` | Path to frozen engine executable (Tauri sidecar) |

### Optional

| Variable | Description |
|----------|-------------|
| `PYTHONUNBUFFERED` | Set `1` for live terminal progress during CLI scans |
| `SEARXNG_URL` | Base URL for `scripts/searx_search.py` and WEB-SPDR (default `http://127.0.0.1:8080`; Docker Compose uses `http://searxng:8080`) |
| `AUDIOTHECA_REQUIRE_ADMIN` | Set `1` to require elevation for live delete/quarantine/shred/repair |
| `AUDIOTHECA_NET_PAUSE` | Set `1` to pause scans when NAS is unreachable (NET-SAFE) |
| `AUDIOTHECA_METRICS_HISTORY` | Rolling telemetry samples for sparklines (default `60`) |
| `AUDIOTHECA_AI_LOOKUP_PROVIDER` | `openai_compatible` for live AI lookup |
| `AUDIOTHECA_AI_OPENAI_API_KEY` | API key when using OpenAI-compatible provider |
| `ACOUSTID_CLIENT_KEY` | Optional AcoustID/MusicBrainz client key (`POST /api/audio/acoustid-lookup`; skipped if unset) |
| `AUDIOTHECA_ACOUSTID_CLIENT` | Alternate name for the AcoustID client key |
| `AUDIOTHECA_AIR_GAP` | Set `1` to disable outbound lookups (AcoustID, AI, harvest) |

---

## Engine settings (`audiotheca/config.py`)

Editable in code or overridden via CLI:

```powershell
python main.py --dry-run --root "D:\path\to\library"
python main.py --live --root "D:\path\to\library"
```

| Setting | Default | Notes |
|---------|---------|-------|
| `DRY_RUN` | `True` | No filesystem changes when true |
| `MAX_WORKERS` | `8` | Use 4–8 on network shares |
| `MAX_WALK_DEPTH` | `8` | Lower if scans hang |
| `PROBE_DEPTH` | `8` | Archive/installer peek depth |
| `ENABLE_ARCHIVE_PEEK` | `True` | Requires 7-Zip for non-zip |
| `ENABLE_SCENE_ARCHIVE_PEEK` | `True` | Scene-hash folder peek |
| `SCENE_AUTO_RENAME` | `False` | Stage 2 live renames |
| `ACTION_MODE` | `section` | `ask` \| `section` \| `item` \| `auto` |
| `CACHE_SCHEMA` | `9.7.1` | Bump only when scan tree format changes |

Full feature context: [Feature Guide](FEATURE_GUIDE.md).

---

## Feedback & persistence

| File | Purpose |
|------|---------|
| `dedupe_reports/feedback/engine_hints.json` | Duplicate rejections → engine |
| `dedupe_reports/feedback/investigation_*.json` | Investigation corrections |
| `dedupe_reports/feedback/user_vendors.json` | User-added vendor keywords |
| `dedupe_reports/feedback/underscore_whitelist.json` | `_`-prefixed folders to scan |
| `dedupe_reports/scan_cache.json` | Directory scan cache |

Delete `scan_cache.json` or use UI **Skipped files → rescan** to force fresh tree walks.

---

## Scan options (UI / API jobs)

Skippable phases (faster dry runs):

- `quarantine`, `duplicates`, `restructure_live`, `purge`
- `archive_peek`, `scene_peek`, `ai_lookup`

**Processing flow** presets in the Scan tab map to these (default: **Almost full**).

Targeted rescans pass `target_paths` + optional `invalidate_cache_paths` (see Skipped files / Space recovery tabs).

---

## 7-Zip

Install from https://www.7-zip.org/ and ensure `7z` is on PATH:

```powershell
where.exe 7z
python -c "from archive_peek import find_7z; print(find_7z())"
```

Without 7-Zip, `.zip` peek still works; `.rar`/`.7z`/`.iso` show `NEEDS_7ZIP` in reports.

---

## Security defaults

- Local/dev API binds **127.0.0.1** only
- Auth for `/api/*` (except public bootstrap paths): session cookie, `Authorization: Bearer`, or scoped `?ticket=`
- Public without auth: `/api/health`, `/api/auth/token` (localhost unless disabled), `/api/auth/session` (localhost or proxy secret)
- Docker/LAN: disable token bootstrap; mint an **opaque HttpOnly** session via nginx + `AUDIOTHECA_PROXY_SECRET` (token never in the JS bundle or cookie value)
- Downloads use **single-use**, path-scoped tickets issued on click; media tickets are also **resource-bound**
- Library paths collapse `.` / `..` and reject symlink-ancestor escapes — see [Security](SECURITY.md)
- Live execute endpoints require explicit `dry_run: false` + `confirm_live: true`

Details: [Security](SECURITY.md)
