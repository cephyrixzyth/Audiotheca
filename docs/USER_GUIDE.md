# Audiotheca — Quick User Guide

Engine **10.0.0** · Web UI **1.0.12**

**New here?** Read the [main README](../README.md) for overview, screenshots, and video placeholders.

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

On Windows, the close button (X) can **minimize to the system tray** or **quit completely**. Choose the default in **System → Environment → Desktop close behavior**, or pick each time in the close dialog. Right-click or double-click the tray icon to show the window again.

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

Primary nav: **Dashboard** · **Scan** · **Review** ▾ · **Library** · **System** ▾ · **Help** (last).

| Section | What you do |
| --- | --- |
| **Dashboard** | Works before first scan — host metrics, environment health, quick links; pick run for route-ready gauges and compare runs |
| **Scan** | Start dry-run; **Processing flow** presets; live WebSocket progress; **AI lookup** panel |
| **Library** | Shared explorer — browse roots, **Pop out**, dual-pane compare, folder filter / library search, type·BPM·key facets, **audio preview**, **DropZone** |
| **Help** | Built-in guides with screenshots and GIFs |

### Review sub-tabs

| Tab | What you do |
| --- | --- |
| **Investigation** | Filter buckets, bulk correct, group by prefix, export feedback; **Investigation lookup** (WEB-SPDR, TAG-GEN, NFO-PARSE) |
| **Duplicates** | Pick keeper, reject bad groups, preview/stage deletes, manual dupes; **Acoustic near-dupes** (Chromaprint) and **Fuzzy pack dupes** (ssdeep/TLSH) as extra lanes |
| **Restructure** | Preview routes; execute approved sections (live, confirmed) |
| **Archives** | Archive peek verdicts; redundant archive size summary; **Diff** wizard |
| **Scene renames** | Hash folder → product name proposals |
| **Scan audit** | Full per-item identification audit |
| **Skipped files** | Scan failures, coverage gaps, cache hits, coexistence, run compare, **rescan** |

### System sub-tabs

| Tab | What you do |
| --- | --- |
| **Space recovery** | Coexistence summary, **underscore vendor whitelist**, disk reclaim links |
| **Security** | Malware heuristics, PE capability hints, quarantine/shred, SHA-256 hash lookup, MEM-SCAN |
| **Environment** | Dependency health, repairs, **theme studio**, install registry + **License reconcile**, mount watcher, **cloud/S3 telemetry**, **orchestration tools**, **94-code spec catalog**, virtual paths, preview session |
| **Vendors** | Vendor gaps, bulk add keywords, KVR / vi-control harvest + research pipeline, unified export |

Most tabs support **drag-to-reorder sections** (Dashboard, Scan, and others); preferences persist in browser localStorage.

**URLs:** every tab is a hash route (`#/scan`, `#/review/investigation`, `#/system/environment`, …). Browser back/forward works. The selected run lives in `?run=<stamp>` so a link can open a specific scan. Press **⌘K** / **Ctrl+K** (or **Search** in the top bar) to jump to any tab, spec code, or the library explorer.

**File explorer:** open **Library** from the top bar, or click **Browse** on any path link. Type to filter the current folder, or run a library-wide search; type/BPM/key **facets** sit above the listing. Click a WAV/FLAC for **Spot preview**. **Audio preview** on WAV/MP3/FLAC rows; **DropZone** when dragging files onto the explorer. Use **Pop out wide panel** for full-width review; dual-pane compare on two folders.

**Themes:** use the ◐ selector in the top bar, or **Environment → Theme studio** for custom palettes. Buttons and accents follow the active theme (no hardcoded green).

**Spec catalog:** browse 94-code status under **Environment → Architecture spec catalog**; API at `GET /api/spec/catalog` — see [Spec catalog](SPEC_CATALOG.md).

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
| API 401 in UI | Restart API; UI re-establishes session (`/api/auth/session`) or localhost token; hard-refresh if a stale cookie remains |
| Docker UI never authenticates | Set matching `AUDIOTHECA_API_TOKEN` + `AUDIOTHECA_PROXY_SECRET`; token bootstrap is disabled in compose |
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
| [Main README](../README.md) | Overview, UI tour, media placeholders |
| [Testing Guide](TESTING.md) | External tester checklist |
| [Configuration](CONFIGURATION.md) | Env vars, paths |
| [Install Guide](INSTALL.md) | Full setup |
| [Feature Guide](FEATURE_GUIDE.md) | Phases, reports, API |
| [Doc assets](assets/README.md) | Screenshot/video capture |
| [Security](SECURITY.md) | Sessions, tickets, path allowlist, live-run guards |
| [FAQ](FAQ.md) | Q&A |
| [Changelog](CHANGELOG.md) | Version history |
