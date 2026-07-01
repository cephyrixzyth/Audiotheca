# Audiotheca Security

Audiotheca is a **local-only operator tool** for managing a personal audio software library. It is not designed as a multi-user or internet-facing service.

## Threat model

- **Intended use:** One trusted operator on their own machine, API bound to `127.0.0.1:8787`.
- **Trust boundary:** Any process on the same host that can reach the API or read `dedupe_reports/.api_token` is treated as authorized.
- **Not in scope:** Multi-tenant isolation, encrypted storage of library metadata, or protection against malware already running as the same user.

## Authentication

The API uses a **Bearer token** stored at:

`dedupe_reports/.api_token`

- Auto-generated on first API start (unless `AUDIOTHECA_API_TOKEN` is set in the environment).
- The UI bootstraps the token via `GET /api/auth/token` (localhost only, no auth required).
- All other `/api/*` routes require `Authorization: Bearer <token>`.
- WebSocket job events require `?token=` matching the job’s creation token.

**Do not commit `.api_token` to git** (it is gitignored).

## Network exposure

- Default bind: `127.0.0.1:8787` — not reachable from other machines.
- Do **not** bind to `0.0.0.0` without adding reverse-proxy auth and TLS.

## Library root allowlist

Paths used for scans, explorer, cache invalidation, rescans, and live moves must fall under configured library roots:

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
