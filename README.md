# Audiotheca

**Audio library dedupe & routing engine** — scan, classify, peek inside archives, deduplicate, and reorganize large VST, sample, and installer libraries on local disks or network shares.

| | |
|---|---|
| **Engine** | 10.0.0 |
| **Web UI / API** | 1.0.0 |
| **Primary platform** | Windows (CLI, browser UI, Tauri desktop) |

---

## Table of contents

- [What Audiotheca does](#what-audiotheca-does)
- [Who should read what](#who-should-read-what)
- [Quick start (Windows)](#quick-start-windows)
- [First scan walkthrough](#first-scan-walkthrough)
- [Web UI tour](#web-ui-tour)
- [Screenshots](#screenshots)
- [Video walkthroughs](#video-walkthroughs)
- [Documentation index](#documentation-index)
- [Project layout](#project-layout)
- [Other commands](#other-commands)
- [Staged live rollout](#staged-live-rollout)
- [Safety defaults](#safety-defaults)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## What Audiotheca does

Audiotheca is built for **large, messy audio-software libraries** — often on slow SMB network shares — where manual cleanup does not scale.

In plain language, it:

1. **Walks your library** under configurable category bins (`a/`, `b/`, `=`, and similar).
2. **Identifies vendors and products** using filenames, PE headers, NFO/readme text, archive listings, and (when needed) **AI-assisted lookup** for stubborn unknowns.
3. **Lists archive contents without extracting** — scene-hash folders, sibling archive+extracted pairs, multipart sets.
4. **Finds duplicate products** with strict matching (not naive name-only dedupe).
5. **Plans vendor-folder routing** and flags items that need human review.
6. **Produces detailed CSV/JSON reports** before anything moves — dry-run is the default everywhere.

When you are ready, live runs support **per-section or per-item approval** with ETA progress in the terminal and a **browser dashboard** for triage, keeper selection, restructure preview, malware heuristics, disk recovery, and more.

> **Nothing is permanently deleted.** Suspected duplicates go to `_delete-canidates` for you to review. With dry-run enabled, **no files move at all**.

---

## Who should read what

| You are… | Start here |
|----------|------------|
| **Trying Audiotheca on your PC for the first time** | [Testing guide](docs/TESTING.md) — clone, paths, smoke test, checklist |
| **Using it day to day** | [User guide](docs/USER_GUIDE.md) |
| **Installing Python, 7-Zip, Node, or Tauri** | [Install guide](docs/INSTALL.md) |
| **Configuring paths and env vars** | [Configuration](docs/CONFIGURATION.md) · copy [.env.example](.env.example) |
| **Understanding scan phases and reports** | [Feature guide](docs/FEATURE_GUIDE.md) |
| **Fixing a failed or hung scan** | [Debug runbook](docs/DEBUG_RUNBOOK.md) · [FAQ](docs/FAQ.md) |
| **Adding screenshots/videos to docs** | [docs/assets/README.md](docs/assets/README.md) |

Set `AUDIOTHECA_LIBRARY_ROOT` to **your** library path before scanning — never rely on repo defaults.

---

## Quick start (Windows)

**Desktop installer (recommended):** download or build with `.\scripts\build-installers.ps1` — see [Install guide](docs/INSTALL.md#pre-built-installers). No Python/Node required for end users.

**Portable:** extract `Audiotheca-Portable-1.0.0-win64.zip` and run `Run Audiotheca.bat`.

**Developer / CLI path:**

### 1. Prerequisites

| Tool | Required for | Get it |
|------|----------------|--------|
| **Python 3.11+** (3.13 recommended) | Engine + API | [python.org](https://www.python.org/downloads/) |
| **7-Zip** | Archive peek (`.rar`, `.7z`, `.iso`) | [7-zip.org](https://www.7-zip.org/) |
| **Node.js 24+ LTS** | Browser UI only | [nodejs.org](https://nodejs.org/) |
| **Rust** | Tauri desktop builds only | [rustup.rs](https://rustup.rs/) |

### 2. Engine (CLI)

```powershell
cd "C:\path\to\audiotheca"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
$env:PYTHONUNBUFFERED = "1"
python main.py --dry-run
```

Reports appear in `dedupe_reports/`. **Always dry-run first.**

### 3. Browser UI (recommended)

```powershell
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
.\start-ui.ps1
```

Opens **http://localhost:5173** (API on port **8787**).

| Script | Purpose |
|--------|---------|
| `start-ui.ps1` | API + Vite dev server (browser UI) |
| `start-api.ps1` | API only — no Node.js required |
| `start-tauri.ps1` | Tauri desktop dev window |

### 4. Desktop app (Tauri)

For end users who should not install Python separately:

```powershell
python scripts/build_sidecars.py
cd ui && npm run tauri:build
```

See [Tauri build guide](docs/TAURI_BUILD.md).

### 5. Verify install

```powershell
python -m pytest tests/ -q
```

---

## First scan walkthrough

A typical first session:

```
1. Set AUDIOTHECA_LIBRARY_ROOT to your audio software root
2. Launch .\start-ui.ps1  (or python main.py --dry-run)
3. Scan tab → choose a processing flow preset (start with "Fast identify" or full dry-run)
4. Wait for completion — watch live progress and phase ETAs
5. Dashboard → pick the new run stamp; review route-ready % and report links
6. Investigation → fix unknown vendors/buckets
7. Duplicates / Restructure / Archives → review plans (still dry-run)
8. Only then consider staged live rollout (see below)
```

Decisions you make in the UI save under `dedupe_reports/decisions/` and `dedupe_reports/feedback/` for the next engine run.

> **Underscore folders** like `_8Dio` are skipped by default. Use **Space recovery** to whitelist them, then run another dry scan.

---

## Web UI tour

Tabs appear left-to-right in the top bar. **Help is last** (after Vendors).

| Tab | What you do there |
|-----|-------------------|
| **Dashboard** | Pick a run, route-ready gauges, run compare, reorderable panels |
| **Scan** | Start jobs, processing flow editor, skippable phases, AI lookup progress |
| **Investigation** | Triage unknown items — set vendor or bucket, bulk correct, export feedback |
| **Duplicates** | Pick keepers, reject bad groups, stage deletes |
| **Restructure** | Preview vendor moves; execute approved sections (live, confirmed) |
| **Archives** | Archive peek verdicts; redundant archive candidates |
| **Scene renames** | Approve hash-folder → product name renames |
| **Scan audit** | Full per-item identification audit table |
| **Skipped files** | Failures, coverage gaps, cache hits, coexistence, targeted rescan |
| **Space recovery** | Underscore whitelist, coexistence summary, hardlink/bloat plans |
| **Security** | Malware heuristics, quarantine, hash lookup URLs |
| **Environment** | Toolchain health, repairs, theme editor, manifest backup |
| **Vendors** | Vendor gaps, web harvest inbox, keyword export |
| **Help** | Built-in install, workflow, layout, and deploy guides |

**Cross-cutting UI features (engine 10 / UI 1.0):**

- **In-app file explorer** — click **Browse** on path links to list folders or archive contents without extracting.
- **Reorderable sections** — drag panel headers or ⠿ handles; save named layouts on Dashboard and Scan.
- **Themes** — quick switcher in the top bar; full editor under **Environment → Themes**.
- **Context sidebar** — search/filter on most data tabs.

Built-in help text also lives in the **Help** tab; full prose docs are in [`docs/`](docs/README.md).

---

## Screenshots

Place PNG/WebP files under `docs/assets/screenshots/` — see [docs/assets/ASSETS.md](docs/assets/ASSETS.md) for the full checklist.

### Dashboard & overview

![Audiotheca web UI overview](docs/assets/screenshots/ui-overview.png)

![Dashboard route-ready gauges](docs/assets/screenshots/dashboard-gauges.png)

### Scan & processing

![Scan tab with processing flow editor](docs/assets/screenshots/scan-panel.png)

### Triage & review

![Investigation inbox with bucket filter](docs/assets/screenshots/investigation-inbox.png)

![Duplicate keeper review](docs/assets/screenshots/duplicates-review.png)

![Restructure route preview](docs/assets/screenshots/restructure-preview.png)

### Library tools

![In-app file explorer browsing a library path](docs/assets/screenshots/file-explorer.png)

![Archive peek verdicts](docs/assets/screenshots/archives-verdicts.png)

### Security & environment

![Security / malware panel](docs/assets/screenshots/security-malware.png)

![Environment tab theme editor](docs/assets/screenshots/environment-themes.png)

### Help

![Help tab — last in the tab bar](docs/assets/screenshots/help-panel.png)

---

## Video walkthroughs

All seven walkthroughs are in-repo — click to open or download on GitHub:

| Topic | Video |
|-------|-------|
| First scan from install to Dashboard | [first-scan-walkthrough.mp4](docs/assets/videos/first-scan-walkthrough.mp4) |
| Scan phases and processing flow presets | [scan-phases-and-flow.mp4](docs/assets/videos/scan-phases-and-flow.mp4) |
| Investigation triage and vendor keywords | [investigation-and-vendors.mp4](docs/assets/videos/investigation-and-vendors.mp4) |
| Restructure preview and staged live execute | [restructure-live-staging.mp4](docs/assets/videos/restructure-live-staging.mp4) |
| File explorer and archive peek | [file-explorer-and-archives.mp4](docs/assets/videos/file-explorer-and-archives.mp4) |
| AI lookup review during scan | [ai-lookup-review.mp4](docs/assets/videos/ai-lookup-review.mp4) |
| Security scan and space recovery | [security-and-space-recovery.mp4](docs/assets/videos/security-and-space-recovery.mp4) |

Animated previews render inline on GitHub. [Download full video](#download-full-video-links) for higher quality.

### First scan from install to Dashboard

![First scan walkthrough](docs/assets/gifs/first-scan-walkthrough.gif)

*Set library root, run a dry scan, read Dashboard KPIs.*

[Download full video](docs/assets/videos/first-scan-walkthrough.mp4)

### Scan phases and processing flow presets

![Scan phases and flow](docs/assets/gifs/scan-phases-and-flow.gif)

*Processing flow editor, skippable phases, live WebSocket progress.*

[Download full video](docs/assets/videos/scan-phases-and-flow.mp4)

### Investigation triage and vendor keywords

![Investigation and vendors](docs/assets/gifs/investigation-and-vendors.gif)

*Triage unknown items, add vendor keywords, export feedback.*

[Download full video](docs/assets/videos/investigation-and-vendors.mp4)

### Restructure preview and staged live execute

![Restructure live staging](docs/assets/gifs/restructure-live-staging.gif)

*Preview routes, approve sections, confirm live guardrails.*

[Download full video](docs/assets/videos/restructure-live-staging.mp4)

### File explorer and archive peek

![File explorer and archives](docs/assets/gifs/file-explorer-and-archives.gif)

*Browse panel, archive listing without extract, redundant archive verdicts.*

[Download full video](docs/assets/videos/file-explorer-and-archives.mp4)

### AI lookup review during scan

![AI lookup review](docs/assets/gifs/ai-lookup-review.gif)

*AI analyzer queue, confirm/reject lookups, cache behavior.*

[Download full video](docs/assets/videos/ai-lookup-review.mp4)

### Security scan and space recovery

![Security and space recovery](docs/assets/gifs/security-and-space-recovery.gif)

*Malware heuristics, underscore whitelist, coexistence summary.*

[Download full video](docs/assets/videos/security-and-space-recovery.mp4)

Build GIFs from MP4 sources: `python scripts/build_doc_gifs.py`. Capture instructions: [docs/assets/README.md](docs/assets/README.md).

---

## Documentation index

| Guide | Description |
| --- | --- |
| **[Main README](README.md)** | Overview, quick start, UI tour (this file) |
| **[Testing](docs/TESTING.md)** | External testers — setup, checklist, smoke tests |
| **[User guide](docs/USER_GUIDE.md)** | Daily workflow, tabs, staged rollout |
| **[Install](docs/INSTALL.md)** | Requirements, 7-Zip, performance tuning |
| **[Configuration](docs/CONFIGURATION.md)** | Environment variables, paths, scan options |
| **[Feature guide](docs/FEATURE_GUIDE.md)** | Phases, archive peek, reports, API |
| **[FAQ](docs/FAQ.md)** | Common questions |
| **[Security](docs/SECURITY.md)** | API token, path allowlist, live-run guards |
| **[Debug runbook](docs/DEBUG_RUNBOOK.md)** | Troubleshooting, hung scans |
| **[Changelog](docs/CHANGELOG.md)** | Version history |
| **[Tauri build](docs/TAURI_BUILD.md)** | Desktop app packaging |
| **[Architecture roadmap](docs/ARCHITECTURE_AND_UI_ROADMAP.md)** | How the stack fits together |
| **[Doc media assets](docs/assets/README.md)** | Screenshot/video capture guide |
| **[Unraid deploy](deploy/unraid/README.md)** | Docker compose for NAS |
| **[SearXNG (optional)](docker/searxng/README.md)** | Private web search for vendor research |

Full index: [docs/README.md](docs/README.md).

---

## Project layout

```
audiotheca/
├── main.py                      # Engine entry point
├── api/                         # FastAPI report viewer + job runner
├── ui/                          # React + Vite + Tauri shell
├── audiotheca/                  # Engine modules (config, routing, scan, ai_lookup, …)
├── archive_peek.py              # Archive listing, scene identity
├── space_recovery.py            # Hardlink dedup + bloat finder
├── scripts/                     # Helpers (searx_search, library_probe, …)
├── docker/searxng/              # Optional private web search
├── deploy/unraid/               # NAS Docker skeleton
├── docs/                        # Documentation + assets/
├── tests/                       # pytest suite
├── dedupe_reports/              # Generated reports (gitignored)
└── .env.example                 # Template for library paths and API port
```

---

## Other commands

```powershell
python peek_archives.py                              # Re-peek archives from last CSV
python gen_archive_delete_candidates.py <peek.csv>   # Redundant archive cleanup script
python space_recovery.py --help                      # Disk reclaim planning
python scripts/searx_search.py --list-presets        # Optional vendor research search
python scripts/library_probe.py                      # Lightweight library stats
```

---

## Staged live rollout

Use a **four-stage rollout** so you never move everything at once:

| Stage | What runs | Typical settings |
| --- | --- | --- |
| **1** | Restructure + investigation | `DRY_RUN=False`, `ACTION_MODE=section`, `SCENE_AUTO_RENAME=False` |
| **2** | Scene renames | `SCENE_AUTO_RENAME=True`, `ACTION_MODE=item` |
| **3** | Delete redundant archives | `move_redundant_archives_{stamp}.ps1` with `$Execute=$true` |
| **4** | Duplicate staging | UI keeper export → live stage |

Details: [User guide — Staged rollout](docs/USER_GUIDE.md#staged-live-rollout).

---

## Safety defaults

- Review dry-run reports before `--live` or UI live execute
- Duplicate deletes go to **`_delete-canidates`**, not permanent deletion
- Scene auto-rename is opt-in via `SCENE_AUTO_RENAME`
- Network share scans use depth limits to avoid SMB timeouts
- API is localhost-only by default — see [Security](docs/SECURITY.md)
- Live API calls require `confirm_live: true` in addition to `dry_run: false`

---

## Troubleshooting

| Problem | Likely fix |
|---------|------------|
| Scans wrong or empty library | Set `AUDIOTHECA_LIBRARY_ROOT` to your path |
| `npm` not recognized | Install Node.js 24+; reopen terminal |
| API 401 in UI | Restart API; UI re-fetches token from localhost |
| Port already in use | `$env:AUDIOTHECA_API_PORT=8790` and `$env:VITE_API_PORT=8790` |
| No terminal progress | `$env:PYTHONUNBUFFERED=1` |
| `NEEDS_7ZIP` in reports | Install 7-Zip; verify with `where.exe 7z` |
| UI shows stale data | Match `VITE_API_PORT` to running API; refresh run list |
| Scan appears hung on SMB | Lower `MAX_WORKERS` (4–8); see [Debug runbook](docs/DEBUG_RUNBOOK.md) |

More: [FAQ](docs/FAQ.md) · [Debug runbook](docs/DEBUG_RUNBOOK.md) · [Testing guide](docs/TESTING.md).

---

## License

Private / internal use unless otherwise specified.
