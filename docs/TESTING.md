# Audiotheca — Testing on Your Own System

This guide is for **another machine or another user** validating Audiotheca without the original author's library paths or network share.

Engine **10.0.0** · Web UI **1.0.12**

**Overview and UI tour:** [main README](../README.md) · **Doc screenshots:** [assets/ASSETS.md](assets/ASSETS.md)

---

## What you need

| Tool | Version | Required for |
|------|---------|--------------|
| Python | 3.11+ (3.13 recommended) | Engine, API, tests |
| 7-Zip | Latest | Archive peek (`.rar`, `.7z`, `.iso`) |
| Node.js | 24+ LTS | Browser UI only |
| Git | Any | Clone the repo |

**Optional:** Rust (Tauri desktop only), Docker (Unraid stack — see [deploy/unraid/README.md](../deploy/unraid/README.md)).

---

## 1. Get the code

```powershell
git clone <repository-url> audiotheca
cd audiotheca
```

Or unzip a release archive into a folder **without spaces** if possible (paths with spaces work when quoted).

---

## 2. Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Verify:

```powershell
python -c "import pefile, rapidfuzz, tqdm, fastapi; print('deps OK')"
python -m pytest tests/ -q
```

Expect **569+ tests passing** (4 skipped without local Run_Summary fixtures). Failures often mean missing packages or wrong Python version.

---

## 3. Point at **your** library (not the author's)

The repo defaults to `Z:\_software\_audio`. **Override before any scan.**

### Option A — environment variable (recommended)

```powershell
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\MyAudio\_software\_audio"
$env:AUDIOTHECA_LIBRARY_ROOTS = $env:AUDIOTHECA_LIBRARY_ROOT
```

### Option B — CLI flag

```powershell
python main.py --dry-run --root "D:\MyAudio\_software\_audio"
```

### Option C — `.env` file (copy from template)

```powershell
copy .env.example .env
# Edit AUDIOTHECA_LIBRARY_ROOT in .env, then:
Get-Content .env | ForEach-Object {
  if ($_ -match '^([^#][^=]+)=(.*)$') { Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim() }
}
```

### First-time smoke test (small folder)

Create a tiny fake library so the first run finishes in seconds:

```powershell
$test = "$env:TEMP\audiotheca-test-lib"
New-Item -ItemType Directory -Force -Path "$test\sectionA\VendorA\ProductOne" | Out-Null
Set-Content "$test\sectionA\VendorA\ProductOne\readme.txt" "test"

$env:AUDIOTHECA_LIBRARY_ROOT = $test
$env:PYTHONUNBUFFERED = "1"
python main.py --dry-run
```

Check `dedupe_reports/Run_Summary_*.txt` was created.

---

## 4. Start the Web UI

**Terminal 1 — API:**

```powershell
cd audiotheca
.\.venv\Scripts\Activate.ps1
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\MyAudio\_software\_audio"
python -m api.server
```

Health check: http://127.0.0.1:8787/api/health

**Terminal 2 — UI:**

```powershell
cd audiotheca\ui
npm install
npm run dev
```

Open http://localhost:5173

Or use the combined launcher (Windows):

```powershell
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\MyAudio\_software\_audio"
.\start-ui.ps1
```

If the API runs on a non-default port:

```powershell
$env:AUDIOTHECA_API_PORT = "8790"
$env:VITE_API_PORT = "8790"
```

---

## 5. Recommended test checklist

Use this order on **your** library (dry-run only until you trust results).

| Step | Action | Pass criteria |
|------|--------|---------------|
| 1 | `python -m pytest tests/ -q` | All tests green |
| 1b | `cd ui && npm test` | Vitest unit tests green (`pathKey.test.ts`) |
| 1c | `cd ui && npm run test:e2e` | Playwright scan-flow smoke passes (API must be running) |
| 2 | Temp-folder dry run (above) | `Run_Summary_*.txt` appears |
| 3 | Full dry run on real library | Engine completes; 0 unexpected failures in log |
| 4 | Open UI → **Dashboard** | Latest run listed; gauges load |
| 5 | **Scan** tab → dry run + **Fast identify** flow | Job completes; WebSocket progress updates |
| 6 | **Investigation** | Filter buckets; export feedback |
| 7 | **Vendors** | View gaps; add a test vendor keyword |
| 8 | **Space recovery** | Underscore list loads; coexistence summary counts |
| 9 | **Skipped files** | Coverage gaps / cache hits visible |
| 10 | **Duplicates** | Groups load; save keeper JSON (no live delete) |

Do **not** run live moves (`--live` or `dry_run: false`) until you have reviewed CSV reports and backed up data.

---

## 5b. UI automated tests (Vitest + Playwright)

From `ui/` after `npm install`:

```powershell
cd ui
npm test                  # Vitest — path key helpers (fast, no browser)
npm run test:e2e          # Playwright — scan flow smoke (needs API on 8787 + dev server)
```

Playwright config: `ui/playwright.config.ts`. E2E spec: `ui/e2e/scan-flow.spec.ts`.
CI runs Vitest (`npm test`) plus the production UI build; Playwright remains a local/manual smoke.

For CI-style runs, start the API in one terminal (`python -m api.server`) before `npm run test:e2e`.

---

## 6. API smoke test (no browser)

```powershell
# Token (localhost only)
$token = (Invoke-RestMethod http://127.0.0.1:8787/api/auth/token).token
$headers = @{ Authorization = "Bearer $token" }

# Optional: short-lived ticket for query-string surfaces (1.0.12+)
$ticket = (Invoke-RestMethod http://127.0.0.1:8787/api/auth/ticket -Method Post -Headers $headers).ticket

Invoke-RestMethod http://127.0.0.1:8787/api/health -Headers $headers
Invoke-RestMethod http://127.0.0.1:8787/api/runs -Headers $headers
Invoke-RestMethod http://127.0.0.1:8787/api/security/library-roots -Headers $headers
```

---

## 7. What gets written on disk

| Path | Purpose |
|------|---------|
| `dedupe_reports/` | CSV/TXT reports per run |
| `dedupe_reports/scan_cache.json` | Warm scan cache (safe to delete to force rescan) |
| `dedupe_reports/.api_token` | Local API auth (auto-created; **do not commit**) |
| `dedupe_reports/feedback/` | Vendor overrides, underscore whitelist, engine hints |
| `dedupe_reports/decisions/` | Duplicate keeper exports from UI |
| `dedupe_engine.log` | Engine log next to `main.py` |

Set `AUDIOTHECA_HOME` to relocate all report data outside the repo:

```powershell
$env:AUDIOTHECA_HOME = "C:\AudiothecaData"
```

---

## 8. Network shares vs local disks

| Storage | Notes |
|---------|--------|
| **Local SSD/NVMe** | Fastest; best for first full dry run |
| **SMB / mapped drive** | Works; use `MAX_WORKERS=4–8`; expect 45–120+ min on large libraries |
| **Read-only share** | Dry runs OK; live runs fail at startup |

---

## 9. Optional: SearXNG (online research helper)

Private meta-search for vendor/library research (not required for core scans):

```powershell
cd docker\searxng
.\start.ps1   # requires Docker Desktop
python scripts\searx_search.py --preset vendor --arg "Native Instruments"
```

See [docker/searxng/README.md](../docker/searxng/README.md).

---

## 10. Reporting issues

Include:

1. `ENGINE_VERSION` from run output or `Run_Summary_*.txt`
2. OS, Python version, local vs network path
3. Relevant lines from `dedupe_engine.log`
4. Whether UI or CLI; API port if not 8787
5. **Never** attach `.api_token` or full library paths if sharing logs publicly

More: [Debug Runbook](DEBUG_RUNBOOK.md) · [FAQ](FAQ.md)

---

## 11. Next steps after validation

| Goal | Doc |
|------|-----|
| Daily use | [Quick User Guide](USER_GUIDE.md) |
| All settings | [Configuration](CONFIGURATION.md) |
| Unraid / Docker deploy | [deploy/unraid/README.md](../deploy/unraid/README.md) |
| Security model | [Security](SECURITY.md) |
