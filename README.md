# Audiotheca

**Audio Library Dedupe & Routing Engine** — scan, classify, peek inside archives, deduplicate, and reorganize large VST/sample/installer libraries on local or network shares.

Current engine version: **10.0.0** · Web UI: **0.2.0**

## What it does

Audiotheca walks your audio software root, identifies vendors and products, **lists archive contents without extracting**, diagnoses scene-hash multipart sets, flags duplicates and structural issues, and produces detailed reports before any files are moved. Live runs support per-section or per-item approval with **per-phase ETA** in the terminal.

A **browser dashboard** lets you triage investigation items, pick duplicate keepers, preview restructure routes, manage vendor keywords, recover disk space, and trigger scans with live progress.

## New here?

| Audience | Start here |
|----------|------------|
| **Testing on your own PC** | **[Testing guide](docs/TESTING.md)** — clone, configure paths, smoke test, checklist |
| **Daily use** | [Quick User Guide](docs/USER_GUIDE.md) |
| **Install & deps** | [Install Guide](docs/INSTALL.md) |
| **All env vars** | [Configuration](docs/CONFIGURATION.md) |

Copy [.env.example](.env.example) and set `AUDIOTHECA_LIBRARY_ROOT` to **your** library path before scanning.

## Quick start

### Engine (CLI)

```powershell
cd "C:\path\to\audiotheca"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Install 7-Zip for .rar/.7z archive listing — https://www.7-zip.org/

$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
$env:PYTHONUNBUFFERED = "1"
python main.py --dry-run
```

Reports appear in `dedupe_reports/`. Always dry-run first.

### Browser UI

Requires [Node.js 24+ (Active LTS)](https://nodejs.org/).

```powershell
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
.\start-ui.ps1
```

Opens **http://localhost:5173** (API on port **8787**). API-only without Node: `.\start-api.ps1`.

### Verify install

```powershell
python -m pytest tests/ -q
```

## Documentation

| Guide | Description |
| --- | --- |
| **[Testing on your system](docs/TESTING.md)** | **External testers** — setup, checklist, smoke tests |
| **[Configuration](docs/CONFIGURATION.md)** | Environment variables, paths, scan options |
| [Documentation index](docs/README.md) | All guides in one list |
| [Quick User Guide](docs/USER_GUIDE.md) | Install, run, UI workflow, staged rollout |
| [Install Guide](docs/INSTALL.md) | Requirements, 7-Zip, performance tuning |
| [Feature Guide](docs/FEATURE_GUIDE.md) | Phases, archive peek, reports, API |
| [FAQ](docs/FAQ.md) | Common questions |
| [Security](docs/SECURITY.md) | API token, path allowlist, live-run guards |
| [Debug Runbook](docs/DEBUG_RUNBOOK.md) | Troubleshooting, hung scans |
| [Changelog](docs/CHANGELOG.md) | Version history |
| [Tauri Build](docs/TAURI_BUILD.md) | Desktop app packaging |
| [Unraid deploy (skeleton)](deploy/unraid/README.md) | Docker compose for NAS |
| [SearXNG (optional)](docker/searxng/README.md) | Private web search for vendor research |

## Web UI (v0.2)

| Tab | Capability |
| --- | --- |
| **Dashboard** | Run picker, route-ready gauges, run compare, reorderable panels |
| **Scan** | Dry-run jobs, processing flow editor, skippable phases |
| **Investigation** | Bucket filter, bulk correct, group-by-prefix, feedback export |
| **Duplicates** | Keeper selection, bad-match rejection, stage deletes |
| **Restructure** | Route preview, section execute (live, confirmed) |
| **Archives** | Archive peek verdicts, delete candidates |
| **Scene renames** | Hash → product rename plan |
| **Scan audit** | Full identification audit table |
| **Skipped files** | Coverage gaps, cache hits, coexistence, rescan |
| **Space recovery** | Underscore vendor whitelist, coexistence queue, disk reclaim |
| **Vendors** | Vendor gaps, harvest, user keywords, unified export |

**Launchers:**

| Script | Purpose |
| --- | --- |
| `start-ui.ps1` | API + Vite dev server (browser UI) |
| `start-api.ps1` | API only — no Node.js required |
| `start-tauri.ps1` | Tauri desktop dev window |

### Desktop app (Tauri)

Requires Rust ([rustup.rs](https://rustup.rs/)) and Node.js.

```powershell
python scripts/build_sidecars.py
cd ui && npm run tauri:build
```

See [Tauri Build](docs/TAURI_BUILD.md).

## Project layout

```
audiotheca/
├── main.py                      # Engine entry point
├── api/                         # FastAPI report viewer + job runner
├── ui/                          # React + Vite + Tauri shell
├── audiotheca/                  # Engine modules (config, routing, scan, …)
├── archive_peek.py              # Archive listing, scene identity
├── space_recovery.py            # Hardlink dedup + bloat finder
├── scripts/                     # Helpers (searx_search, library_probe, …)
├── docker/searxng/              # Optional private web search
├── deploy/unraid/               # NAS Docker skeleton
├── tests/                       # pytest suite
├── dedupe_reports/              # Generated reports (gitignored)
└── docs/                        # Documentation
```

## Other commands

```powershell
python peek_archives.py                              # Re-peek archives from last CSV
python gen_archive_delete_candidates.py <peek.csv>   # Redundant archive cleanup script
python space_recovery.py --help                      # Disk reclaim planning
python scripts/searx_search.py --list-presets        # Optional vendor research search
python scripts/library_probe.py                      # Lightweight library stats
```

## Staged live rollout

Four-stage rollout (restructure → scene renames → archive cleanup → duplicates). Defaults target **Stage 1** (plan + section approval, scene renames plan-only). See [User Guide — Staged rollout](docs/USER_GUIDE.md#staged-live-rollout).

## Safety defaults

- Review dry-run reports before `--live` or UI live execute
- Duplicate deletes go to **`_delete-canidates`**, not permanent deletion
- Scene auto-rename is opt-in via `SCENE_AUTO_RENAME`
- Network share scans use depth limits to avoid SMB timeouts
- API is localhost-only by default; see [Security](docs/SECURITY.md)

## License

Private / internal use unless otherwise specified.
