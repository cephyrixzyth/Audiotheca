# Audiotheca — Install Guide

Engine version: **10.0.0** · Web UI: **0.2.0**

For overview and first-run walkthrough, see the [main README](../README.md).

For a step-by-step **first run on another machine**, see **[Testing Guide](TESTING.md)**.

---

## Requirements

| Requirement | Notes |
| --- | --- |
| **Python** | 3.11+ (3.13 recommended) |
| **OS** | Windows (primary); Linux possible for engine/API with path adjustments |
| **Storage** | Local disk or SMB/CIFS mapped drive |
| **7-Zip** | **Required for archive peek** (`.rar`, `.7z`, `.iso`) — [7-zip.org](https://www.7-zip.org/) |
| **Node.js 24+** | Browser UI only — [nodejs.org](https://nodejs.org/) (Active LTS) |
| **Rust** | Tauri desktop builds only — [rustup.rs](https://rustup.rs/) |
| **Write access** | Live runs only (`DRY_RUN = False` or `--live`) |

### Python packages

```powershell
pip install -r requirements.txt
```

| Package | Purpose |
| --- | --- |
| `pefile` | PE `CompanyName` vendor ID |
| `rapidfuzz` | Fuzzy duplicate name matching |
| `tqdm` | Scan progress bar with ETA |
| `psutil` | CPU/RAM metrics in Dashboard (optional) |
| `fastapi` / `uvicorn` | Local API for web UI |
| `pytest` / `httpx` | Unit tests |
| `pyinstaller` | Sidecar builds (maintainers) |

---

## Installation

```powershell
cd "C:\path\to\audiotheca"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Verify:

```powershell
python -c "import pefile; import rapidfuzz; import tqdm; print('OK')"
where.exe 7z
python -c "from archive_peek import find_7z; print(find_7z())"
python -m pytest tests/ -q
```

Optional — Node.js for UI:

```powershell
node --version
cd ui && npm install
```

---

## Configuration

**Do not use the author's default path.** Set your library root before scanning:

```powershell
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
$env:AUDIOTHECA_LIBRARY_ROOTS = $env:AUDIOTHECA_LIBRARY_ROOT
```

Or copy [.env.example](../.env.example) → `.env` and edit paths.

Full reference: **[Configuration](CONFIGURATION.md)**

### Engine (code or CLI)

```powershell
python main.py --dry-run --root "D:\YourLibrary\_software\_audio"
python main.py --live --root "D:\YourLibrary\_software\_audio"
```

Key settings in `audiotheca/config.py`:

| Setting | Default | Notes |
| --- | --- | --- |
| `DRY_RUN` | `True` | Safe default |
| `MAX_WORKERS` | `8` | Use 4–8 on SMB |
| `MAX_WALK_DEPTH` / `PROBE_DEPTH` | `8` | Lower if hangs |
| `ENABLE_ARCHIVE_PEEK` | `True` | Needs 7-Zip |
| `SCENE_AUTO_RENAME` | `False` | Stage 2 |
| `ACTION_MODE` | `section` | Live approval granularity |

### Staged live rollout

| Stage | Settings | Action |
| --- | --- | --- |
| **1** | `DRY_RUN=False`, `ACTION_MODE=section`, `SCENE_AUTO_RENAME=False` | Restructure + investigation routing |
| **2** | `SCENE_AUTO_RENAME=True`, `ACTION_MODE=item` | Scene-hash renames |
| **3** | — | `move_redundant_archives_{stamp}.ps1` |
| **4** | — | Duplicate staging via UI |

Bump `CACHE_SCHEMA` only when scan tree output format changes.

---

## Running

### Engine

```powershell
$env:PYTHONUNBUFFERED = "1"
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
python main.py --dry-run
```

Reports: `dedupe_reports/` (or `$AUDIOTHECA_HOME/dedupe_reports/`).

### Web UI

```powershell
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
.\start-ui.ps1          # API + browser
.\start-api.ps1         # API only
```

Manual:

```powershell
python -m api.server
# separate terminal:
cd ui && npm run dev
```

UI: http://localhost:5173 · API health: http://127.0.0.1:8787/api/health

Non-default API port:

```powershell
$env:AUDIOTHECA_API_PORT = "8790"
$env:VITE_API_PORT = "8790"
```

### Utilities

```powershell
python peek_archives.py
python gen_archive_delete_candidates.py dedupe_reports\Archive_Peek_*.csv
python space_recovery.py --root "D:\YourLibrary\_software\_audio" --no-links
python scripts/library_probe.py
```

---

## Performance (network shares)

| Setting | Recommendation |
| --- | --- |
| `MAX_WORKERS` | 4–8 |
| `MAX_WALK_DEPTH` | 5–8 if scans hang |
| `PYTHONUNBUFFERED` | Always `1` |
| Cache | Keep `scan_cache.json` between runs; delete after `CACHE_SCHEMA` bump |

---

## Live-run approval

| `ACTION_MODE` | Behavior |
| --- | --- |
| `ask` | Prompt at start |
| `section` | Approve each category bin |
| `item` | Confirm every action |
| `auto` | No prompts (use with care) |

---

## First live run checklist

1. Successful dry run with 10.0.0 header
2. Review `Scene_Rename_Plan_*.csv` and `Archive_Peek_*.csv`
3. Check `Multipart_Archive_Diagnostic_*.csv` for `MISSING_PART01`
4. **Backup library**
5. Stage 1: `ACTION_MODE = "section"`
6. `python main.py --live` or UI execute with confirmation

See [Quick User Guide](USER_GUIDE.md) and [Testing Guide](TESTING.md).
