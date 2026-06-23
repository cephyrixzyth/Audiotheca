# Audiotheca

**Audio Library Dedupe & Routing Engine** — scan, classify, peek inside archives, deduplicate, and reorganize large VST/sample/installer libraries on local or network shares.

Current engine version: **9.8.0** · Web UI: **v0.2**

## What it does

Audiotheca walks your audio software root (for example `Z:\_software\_audio`), identifies vendors and products, **lists archive contents without extracting**, diagnoses scene-hash multipart sets, flags duplicates and structural issues, and produces detailed reports before any files are moved. Live runs support per-section or per-item approval with **per-phase ETA** in the terminal.

A **browser dashboard** lets you triage investigation items, pick duplicate keepers, preview restructure routes, and trigger scans with live progress.

## Quick start

**New users:** start with the [Quick User Guide](docs/USER_GUIDE.md).

### Engine (CLI)

```powershell
cd "C:\path\to\audiotheca"    # always quote paths with spaces
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Install 7-Zip for .rar/.7z archive listing
# https://www.7-zip.org/

$env:PYTHONUNBUFFERED=1
python main.py --dry-run
```

Always dry-run first and review reports in `dedupe_reports/`.

### Browser UI

Requires [Node.js 20+](https://nodejs.org/).

```powershell
.\start-ui.ps1
```

Opens **http://localhost:5173** (API on port 8787). API-only without Node: `.\start-api.ps1`.

### Other commands

```powershell
python peek_archives.py                              # Re-peek archives from last CSV
python gen_archive_delete_candidates.py <peek.csv>   # Redundant archive cleanup script
python -m pytest tests/ -q                           # Unit tests
```

## Documentation

| Guide | Description |
| --- | --- |
| **[Quick User Guide](docs/USER_GUIDE.md)** | **Start here** — install, run, UI, staged rollout |
| [Install Guide](docs/INSTALL.md) | Requirements, 7-Zip, setup, configuration |
| [Feature Guide](docs/FEATURE_GUIDE.md) | Phases, archive peek, scene rename, reports |
| [FAQ](docs/FAQ.md) | Common questions and decisions |
| [Debug Runbook](docs/DEBUG_RUNBOOK.md) | Troubleshooting, multipart archives, hung scans |
| [Changelog](docs/CHANGELOG.md) | Version history |
| [Tauri Build](docs/TAURI_BUILD.md) | Desktop app packaging |
| [Architecture & UI Roadmap](docs/ARCHITECTURE_AND_UI_ROADMAP.md) | Engine/UI architecture |
| [Backend Enhancement Roadmap](docs/BACKEND_ENHANCEMENT_ROADMAP.md) | Per-module corrections & feedback to refine the engine |

## Web UI (v0.2)

| Tab | Capability |
| --- | --- |
| **Dashboard** | Run picker, summary stats |
| **Scan** | Start dry-run from UI; live WebSocket phase progress |
| **Investigation** | Filter buckets, search, Open in Explorer |
| **Duplicates** | Pick keeper per group; save/download `approved_{stamp}.json` |
| **Archives** | Archive peek verdicts + delete-candidate size summary |
| **Restructure / Scene** | Route preview with Explorer links |

**Launchers:**

| Script | Purpose |
| --- | --- |
| `start-ui.ps1` | API + Vite dev server (browser UI) |
| `start-api.ps1` | API only — no Node.js required |
| `start-tauri.ps1` | Tauri desktop dev window |

### Desktop app (Tauri)

Requires Rust ([rustup.rs](https://rustup.rs/)) and Node.js. Bundled Python sidecars for release builds.

```powershell
python scripts/build_sidecars.py   # api-server + engine exes
cd ui && npm run tauri:build       # MSI/NSIS installer
```

Full guide: [Tauri Build](docs/TAURI_BUILD.md)

## Project layout

```
audiotheca/
├── main.py                      # Engine entry point
├── api/                         # FastAPI report viewer + job runner
├── ui/                          # React + Vite + Tauri desktop shell
│   └── src-tauri/binaries/      # PyInstaller sidecars (release)
├── archive_peek.py              # Archive listing, scene identity
├── progress.py                  # Phase progress + ETA
├── space_recovery.py            # Hardlink dedup + bloat finder
├── gen_archive_delete_candidates.py
├── peek_archives.py             # Standalone archive peek CLI
├── vendor_db.py                 # Vendor keyword database (~700+ vendors)
├── start-ui.ps1 / start-api.ps1 / start-tauri.ps1
├── tests/                       # pytest unit tests
├── dedupe_reports/              # Generated CSV/Markdown reports (gitignored)
└── docs/                        # Documentation
```

## Staged live rollout

`main.py` documents a four-stage rollout (restructure → scene renames → archive cleanup → duplicates). Current defaults target **Stage 1** (live restructure, section approval, scene renames plan-only). See [User Guide — Staged rollout](docs/USER_GUIDE.md#staged-live-rollout-current-config).

## Safety defaults

- Review dry-run reports before disabling `--dry-run`
- Duplicate deletes go to **`_delete-canidates`**, not permanent deletion
- Scene auto-rename is opt-in via `SCENE_AUTO_RENAME`
- Network share scans use depth limits to avoid SMB timeouts

## License

Private / internal use unless otherwise specified.
