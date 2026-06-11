# Audiotheca — Install Guide

Engine version: **9.7.0**

## Requirements

| Requirement | Notes |
| --- | --- |
| **Python** | 3.10+ recommended |
| **OS** | Windows (primary) |
| **Storage** | Local or SMB/CIFS mapped drive |
| **7-Zip** | **Required for archive peek** (`.rar`, `.7z`, `.iso` listing) — [7-zip.org](https://www.7-zip.org/) |
| **Write access** | Live runs only (`DRY_RUN = False`) |

### Python packages

```powershell
pip install -r requirements.txt
```

| Package | Purpose |
| --- | --- |
| `pefile` | PE `CompanyName` vendor ID |
| `rapidfuzz` | Fuzzy duplicate name matching |
| `tqdm` | Scan progress bar with ETA |
| `pytest` | Unit tests (`python -m pytest tests/ -q`) |

---

## Installation

```powershell
cd audiotheca
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Verify:

```powershell
python -c "import pefile; import rapidfuzz; import tqdm; print('OK')"
where.exe 7z
python -c "from archive_peek import find_7z; print(find_7z())"
```

---

## Configuration

Edit the **CONFIGURATION** block in `main.py`:

```python
ENGINE_VERSION = "9.7.0"
ROOT_DIR = r"Z:\_software\_audio"
DRY_RUN = True
MAX_WORKERS = 8
MAX_WALK_DEPTH = 8
PROBE_DEPTH = 8

# Archive intelligence (9.7+)
ENABLE_ARCHIVE_PEEK = True
ENABLE_SCENE_ARCHIVE_PEEK = True
SCENE_AUTO_RENAME = True          # Renames scene-hash folders when identity known
SCENE_PEEK_MIN_SIZE_MB = 500      # Min folder size to peek inside
SCENE_RENAME_MIN_SIZE_MB = 1000   # Min size to auto-rename

ACTION_MODE = "ask"               # ask | section | item | auto
GENERATE_INVENTORY_DUMP = True
```

Bump `ENGINE_VERSION` when changing scan logic (invalidates `scan_cache.json`).

---

## Running

```powershell
$env:PYTHONUNBUFFERED=1
python main.py
```

Terminal output shows per-phase ETA lines like:

```
▶ Phase 1a — Resolve targets per category
  12 / 28 section  (43%)  ·  elapsed 2m05s  ·  ETA 2m48s  ·  s: 412 targets
```

Reports: `dedupe_reports/` (and share copy at `{ROOT}/_dedupe_reports/` when writable).

### Re-peek without full scan

```powershell
python peek_archives.py
# or
python peek_archives.py dedupe_reports\Archive_Coexistence_20260609_2323.csv
```

---

## Performance (network shares)

| Setting | Recommendation |
| --- | --- |
| `MAX_WORKERS` | 4–8 |
| `MAX_WALK_DEPTH` | 5–8 if scans hang |
| `PYTHONUNBUFFERED` | Always `1` |
| Cache | Keep `scan_cache.json` between runs; delete after engine upgrades |

---

## Live-run approval

| `ACTION_MODE` | Behavior |
| --- | --- |
| `ask` | Prompt at start: section / item / auto |
| `section` | Approve each category bin bulk |
| `item` | Confirm every move/quarantine/rename |
| `auto` | No prompts (use with care) |

Scene auto-rename uses the same approval flow as other live actions.

---

## First live run checklist

1. Successful dry run with 9.7.0 header
2. Review `Scene_Rename_Plan_*.csv` and `Archive_Peek_*.csv`
3. Check `Multipart_Archive_Diagnostic_*.csv` for `MISSING_PART01` (incomplete downloads)
4. Backup library
5. `ACTION_MODE = "item"` recommended
6. `DRY_RUN = False`
