# Audiotheca — Quick User Guide

Engine **9.8.0** · Web UI **0.2.0**

**Testing on a new machine?** Start with **[Testing Guide](TESTING.md)** — paths, smoke tests, and checklist.

---

## What you need

| Tool | Required for | Install |
| --- | --- | --- |
| **Python 3.11+** | Engine + API (3.13 recommended) | [python.org](https://www.python.org/downloads/) |
| **7-Zip** | Archive peek | [7-zip.org](https://www.7-zip.org/) |
| **Node.js 24+** | Browser UI | [nodejs.org](https://nodejs.org/) (Active LTS) |

```powershell
cd "C:\path\to\audiotheca"
pip install -r requirements.txt
```

Set **your** library path (required):

```powershell
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
$env:AUDIOTHECA_LIBRARY_ROOTS = $env:AUDIOTHECA_LIBRARY_ROOT
```

See [Configuration](CONFIGURATION.md) for all environment variables.

---

## Three ways to run

### 1. Engine only (CLI)

```powershell
$env:PYTHONUNBUFFERED = "1"
python main.py --dry-run
python main.py --dry-run --root "D:\YourLibrary\_software\_audio"
python main.py --live    # only after reviewing reports
```

Reports: `dedupe_reports/Run_Summary_YYYYMMDD_HHMM.txt`

### 2. Browser UI (recommended)

```powershell
.\start-ui.ps1
```

→ **http://localhost:5173** (API on **8787**)

**API only** (no Node.js):

```powershell
.\start-api.ps1
```

**Manual:**

```powershell
# Terminal 1
python -m api.server

# Terminal 2
cd ui && npm run dev
```

### 3. Desktop app (Tauri)

```powershell
.\start-tauri.ps1
```

See [Tauri Build](TAURI_BUILD.md).

---

## Typical workflow

```
1. Dry run          → Scan tab or python main.py --dry-run
2. Review reports   → Dashboard + CSV in dedupe_reports/
3. Fix vendors      → Vendors tab or vendor_db.py / user_vendors.json
4. Underscore bins  → Space recovery → whitelist _8Dio-style folders → full dry scan
5. Stage 1 live     → Restructure (section approval)
6. Stage 2          → Scene renames (item approval)
7. Stage 3          → Archive cleanup (PowerShell script)
8. Stage 4          → Duplicate staging (optional)
```

Always review `Run_Summary_*.txt` before any live run.

---

## Web UI tabs

| Tab | What you do |
| --- | --- |
| **Dashboard** | Pick run, route-ready / identification gauges, compare runs, reorder panels |
| **Scan** | Start dry-run; **Processing flow** presets (Full audit, Fast identify, …); live WebSocket progress |
| **Investigation** | Filter buckets, bulk correct, group by prefix, export feedback |
| **Duplicates** | Pick keeper, reject bad groups, preview/stage deletes, manual dupes |
| **Restructure** | Preview routes; execute approved sections (live, confirmed) |
| **Archives** | Archive peek verdicts; redundant archive size summary |
| **Scene renames** | Hash folder → product name proposals |
| **Scan audit** | Full per-item identification audit |
| **Skipped files** | Scan failures, coverage gaps, cache hits, coexistence, run compare, **rescan** |
| **Space recovery** | Coexistence summary (deep installers), **underscore vendor whitelist**, disk reclaim links |
| **Vendors** | Vendor gaps, bulk add keywords, web harvest inbox, unified export |

Most tabs support **drag-to-reorder sections** (Dashboard, Scan); preferences persist in browser localStorage.

Decisions save to `dedupe_reports/decisions/approved_{stamp}.json` and `dedupe_reports/feedback/`.

---

## Space recovery & underscore vendors

Folders named `_8Dio`, `_Kontakt Libraries`, etc. are skipped by default during target discovery.

1. Open **Space recovery** tab
2. **Seed known vendors** or **Whitelist all & full dry scan**
3. After scan completes, check Dashboard for improved route-ready %

Disk reclaim (optional CLI):

```powershell
python space_recovery.py --root "%AUDIOTHECA_LIBRARY_ROOT%" --no-links
```

---

## Staged live rollout

| Stage | What runs | Key settings |
| --- | --- | --- |
| **1** | Restructure + investigation | `DRY_RUN=False`, `ACTION_MODE=section`, `SCENE_AUTO_RENAME=False` |
| **2** | Scene renames | `SCENE_AUTO_RENAME=True`, `ACTION_MODE=item` |
| **3** | Delete redundant archives | `move_redundant_archives_{stamp}.ps1` with `$Execute=$true` |
| **4** | Duplicate staging | UI keeper export → live stage |

---

## Key reports

| File | Use it for |
| --- | --- |
| `Run_Summary_*.txt` | Start here — counts and index |
| `Investigation_Breakdown_*.csv` | Manual review buckets |
| `Duplicate_Review_*.csv` | Duplicate groups |
| `Restructure_Plan_*.csv` | Planned moves |
| `Coverage_Gaps_*.csv` | Paths never scanned (incl. underscore) |
| `Archive_Coexistence_*.csv` | Installers / archive siblings |
| `Archive_Peek_*.csv` | Archive vs extracted verdicts |
| `Scene_Rename_Plan_*.csv` | Hash → product renames |

Full list: [Feature Guide](FEATURE_GUIDE.md).

---

## Safety rules

- **Dry run first** after any config or vendor change
- **No permanent deletes** — duplicates → `_delete-canidates`
- **Backup** before Stage 1 live
- **Quote paths** with spaces
- **One command per line** in terminal

---

## Common problems

| Problem | Fix |
| --- | --- |
| Scans wrong / empty library | Set `AUDIOTHECA_LIBRARY_ROOT` to your path |
| `npm: not recognized` | Install Node.js; reopen terminal |
| API 401 in UI | Restart API; UI re-fetches token from localhost |
| Port in use | `$env:AUDIOTHECA_API_PORT=8790` + `$env:VITE_API_PORT=8790` |
| No terminal output | `$env:PYTHONUNBUFFERED=1` |
| `NEEDS_7ZIP` | Install 7-Zip; `where.exe 7z` |
| UI shows old API | Match `VITE_API_PORT` to running API |

More: [FAQ](FAQ.md) · [Debug Runbook](DEBUG_RUNBOOK.md) · [Testing Guide](TESTING.md)

---

## Tests

```powershell
python -m pytest tests/ -q
```

---

## Documentation index

| Guide | Contents |
| --- | --- |
| [Testing Guide](TESTING.md) | External tester checklist |
| [Configuration](CONFIGURATION.md) | Env vars, paths |
| [Install Guide](INSTALL.md) | Full setup |
| [Feature Guide](FEATURE_GUIDE.md) | Phases, reports, API |
| [Security](SECURITY.md) | Token, allowlist |
| [FAQ](FAQ.md) | Q&A |
| [Changelog](CHANGELOG.md) | Version history |
