# Audiotheca Security

Audiotheca is a **local-only operator tool** for managing a personal audio software library. It is not designed as a multi-user or internet-facing service.

Overview and troubleshooting: [main README](../README.md) · [User Guide — Security tab](USER_GUIDE.md#web-ui-tabs).

## Threat model

- **Intended use:** One trusted operator on their own machine, API bound to `127.0.0.1:8787`.
- **Trust boundary:** Any process on the same host that can reach the API or read `dedupe_reports/.api_token` is treated as authorized.
- **Not in scope:** Multi-tenant isolation, encrypted storage of library metadata, or protection against malware already running as the same user.

## Authentication

The API uses a **Bearer token** stored at:

`dedupe_reports/.api_token`

- Auto-generated on first API start (unless `AUDIOTHECA_API_TOKEN` is set in the environment).
- The UI bootstraps the token via `GET /api/auth/token` (**localhost only** by default; no auth required).
- Docker / Unraid installs should set `AUDIOTHECA_API_TOKEN` and bake the same value into the UI as `VITE_API_TOKEN`, with `AUDIOTHECA_DISABLE_TOKEN_BOOTSTRAP=1`.
- `AUDIOTHECA_TRUST_INTERNAL_NETWORK=1` and `AUDIOTHECA_ALLOW_REMOTE_TOKEN_BOOTSTRAP=1` are explicit opt-ins — do not enable them on LAN without reverse-proxy auth.
- All other `/api/*` routes require `Authorization: Bearer <token>` unless a valid short-lived ticket is supplied (see below).

**Do not commit `.api_token` to git** (it is gitignored).

### Short-lived access tickets (1.0.12+)

Some surfaces cannot send an `Authorization` header (WebSocket URLs, `<audio>` / `<img>` src, file download links). For those, the UI exchanges the long-lived bearer for a **single-purpose ticket**:

1. `POST /api/auth/ticket` (requires Bearer auth) → `{ "ticket": "…", "expires_in": 300 }`
2. Append `?ticket=<ticket>` to WebSocket, media, or download URLs

Tickets expire after **300 seconds** by default (`AUDIOTHECA_TICKET_TTL_S` env, clamped 30 s–1 h). They are held in memory only and are not written to disk.

**Legacy:** `?token=<api_token>` is still accepted for older bookmarks and external tools. Prefer tickets for anything that might appear in browser history or server access logs.

| Surface | Auth |
|---------|------|
| REST `/api/*` | `Authorization: Bearer <token>` |
| WebSocket job events | `?ticket=` (preferred) or `?token=` (legacy) |
| Media preview / downloads | `?ticket=` (preferred) or `?token=` (legacy) |

## Network exposure

- Default bind: `127.0.0.1:8787` — not reachable from other machines.
- Do **not** bind to `0.0.0.0` without adding reverse-proxy auth and TLS.
- Unraid compose does **not** publish the API port by default; use the UI proxy and a fixed `AUDIOTHECA_API_TOKEN`.

## Library root allowlist

Paths used for scans, explorer (`/api/browse`), cache invalidation, rescans, and live moves must fall under configured library roots:

1. `AUDIOTHECA_LIBRARY_ROOTS` (comma-separated), or
2. `dedupe_reports/.library_roots.json`, or
3. Default: `ROOT_DIR` from `audiotheca/config.py`

## Live filesystem operations

Endpoints that move/rename/stage files require:

- `dry_run: false` (must be JSON boolean, not string)
- `confirm_live: true` for non-dry-run execute calls

Audit entries are appended to `dedupe_reports/security_audit.jsonl`.

## Data at rest (plain text)

All reports, cache, and feedback are **unencrypted UTF-8**:

| Path | Contents |
|------|----------|
| `dedupe_reports/*.csv` | Full library paths, vendors, analysis |
| `dedupe_reports/scan_cache.json` | Cached scan metadata |
| `dedupe_reports/feedback/*.json` | User corrections and overrides |
| `dedupe_reports/security_audit.jsonl` | Security-relevant API actions |

Treat these as sensitive if your library layout or naming is private.

## Vendor harvest (outbound HTTPS)

Harvest accepts **HTTPS URLs only**. Private/reserved IP ranges are blocked after DNS resolution.

Rate limit: 3 harvest runs per 2 minutes.

## Rate limits

| Action | Limit |
|--------|-------|
| Start scan job | 4 / minute |
| Targeted rescan | 6 / minute |
| Vendor harvest | 3 / 2 minutes |

## Dependency audit

```powershell
cd ui
npm run audit:deps
```

Run periodically; CI runs the same check on push.

## Reporting issues

If you expose Audiotheca beyond localhost or find a bypass of path allowlists, treat it as a security bug and restrict network access until fixed.
