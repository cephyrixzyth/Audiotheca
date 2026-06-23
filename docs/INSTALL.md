# Audiotheca — Install Guide

Engine version: **9.8.0**

## Requirements

| Requirement | Notes |
| --- | --- |
| **Python** | 3.10+ recommended (3.11+ for sidecar builds) |
| **OS** | Windows (primary) |
| **Storage** | Local or SMB/CIFS mapped drive |
| **7-Zip** | **Required for archive peek** (`.rar`, `.7z`, `.iso` listing) — [7-zip.org](https://www.7-zip.org/) |
| **Node.js 20+** | Browser UI and Tauri dev only — [nodejs.org](https://nodejs.org/) |
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
| `fastapi` / `uvicorn` | Local API for web UI |
| `pytest` / `httpx` | Unit tests |
| `pyinstaller` | Sidecar builds (maintainers) |

---

## Installation

```powershell
cd "C:\path\to\audiotheca"    # quote paths with spaces
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Verify:

```powershell
python -c "import pefile; import rapidfuzz; import tqdm; print('OK')"
where.exe 7z
python -c "from archive_peek import find_7z; print(find_7z())"
python -m api.server --help 2>$null; python -c "import fastapi; print('API OK')"
```

Optional — Node.js for UI:

```powershell
node --version
npm --version
```

---

## Configuration

Edit the **CONFIGURATION** block in `main.py`, or pass CLI flags:

```powershell
python main.py --dry-run --root "Z:\_software\_audio"
python main.py --live
```

```python
ENGINE_VERSION = "9.8.0"
CACHE_SCHEMA = "9.7.1"           # Bump only when scan tree format changes
ROOT_DIR = r"Z:\_software\_audio"
DRY_RUN = False                  # Stage 1 live — see staged rollout below
MAX_WORKERS = 8
MAX_WALK_DEPTH = 8
PROBE_DEPTH = 8

# Archive intelligence
ENABLE_ARCHIVE_PEEK = True
ENABLE_SCENE_ARCHIVE_PEEK = True
SCENE_AUTO_RENAME = False        # Stage 2: set True for live renames
SCENE_PEEK_MIN_SIZE_MB = 500
SCENE_RENAME_MIN_SIZE_MB = 1000

ACTION_MODE = "section"          # ask | section | item | auto
GENERATE_INVENTORY_DUMP = True
```

### Staged live rollout

| Stage | Settings | Action |
| --- | --- | --- |
| **1** | `DRY_RUN=False`, `ACTION_MODE=section`, `SCENE_AUTO_RENAME=False` | Restructure + investigation routing |
| **2** | `SCENE_AUTO_RENAME=True`, `ACTION_MODE=item` | Scene-hash renames |
| **3** | — | `move_redundant_archives_{stamp}.ps1` |
| **4** | — | Duplicate staging via UI `approved.json` |

Bump `CACHE_SCHEMA` when `_scan_tree` output format changes. Identification-only releases keep warm `scan_cache.json`.

---

## Running

### Engine

```powershell
$env:PYTHONUNBUFFERED=1
python main.py
```

Terminal output shows per-phase ETA:

```
▶ Phase 1a — Resolve targets per category
  12 / 28 section  (43%)  ·  elapsed 2m05s  ·  ETA 2m48s  ·  s: 412 targets
```

Reports: `dedupe_reports/` (copied to `{ROOT}/_dedupe_reports/` when writable).

### Web UI

```powershell
.\start-ui.ps1          # API + browser UI
.\start-api.ps1         # API only (no Node.js)
```

Manual: `python -m api.server` + `cd ui && npm run dev`

### Re-peek without full scan

```powershell
python peek_archives.py
python peek_archives.py dedupe_reports\Archive_Coexistence_20260609_2323.csv
```

### Archive delete candidates

```powershell
python gen_archive_delete_candidates.py dedupe_reports\Archive_Peek_20260611_0208.csv
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
| `ask` | Prompt at start: section / item / auto |
| `section` | Approve each category bin bulk |
| `item` | Confirm every move/quarantine/rename |
| `auto` | No prompts (use with care) |

Scene auto-rename uses item-by-item approval on live runs when enabled.

---

## First live run checklist

1. Successful dry run with 9.8.0 header
2. Review `Scene_Rename_Plan_*.csv` and `Archive_Peek_*.csv`
3. Check `Multipart_Archive_Diagnostic_*.csv` for `MISSING_PART01`
4. Backup library
5. Stage 1: `ACTION_MODE = "section"` recommended
6. `DRY_RUN = False` or `python main.py --live`

See [Quick User Guide](USER_GUIDE.md) for the full workflow.
