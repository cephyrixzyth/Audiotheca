# Audiotheca — Install Guide

## Requirements

| Requirement | Notes |
| --- | --- |
| **Python** | 3.10 or newer recommended |
| **OS** | Windows (primary target; scans Mac/Linux-only content for quarantine) |
| **Storage** | Local disk or SMB/CIFS network share mapped as a drive letter |
| **Write access** | Required only for live runs (`DRY_RUN = False`) |

### Optional Python packages

| Package | Purpose if installed | If missing |
| --- | --- | --- |
| `pefile` | Reads `CompanyName` from `.exe`/`.dll`/`.vst3` headers | PE-based vendor ID disabled |
| `rapidfuzz` | Accurate fuzzy name matching for duplicates | Token-overlap fallback (less accurate) |
| `tqdm` | Progress bar during scan | Text-only progress |

---

## Installation

### 1. Clone or copy the project

```powershell
# Example: after creating the repo
git clone <your-repo-url> audiotheca
cd audiotheca
```

If migrating from Desktop, copy at minimum:

- `main.py`
- `vendor_db.py`

into the `audiotheca/` folder.

### 2. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On macOS/Linux (if adapting later):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Verify imports

```powershell
python -c "import pefile; import rapidfuzz; import tqdm; print('OK')"
```

---

## Configuration

Open `main.py` and edit the **CONFIGURATION** block at the top.

### Essential settings

```python
ENGINE_VERSION = "9.6.0"          # Shown in reports — bump when you change logic
ROOT_DIR = r"Z:\_software\_audio" # Your library root (must be reachable)
DRY_RUN = True                    # True = reports only; False = can move files
REPORT_DIR = Path(__file__).resolve().parent / "dedupe_reports"
```

### Performance (network shares)

```python
MAX_WALK_DEPTH = 8    # How deep to walk each item for sizing/OS detection
PROBE_DEPTH = 8       # How deep to probe for archives, installers, PE, NFO
MAX_WORKERS = 8       # Parallel scan threads (lower if SMB is unstable)
```

On high-latency shares, try `MAX_WORKERS = 4` first.

### Duplicate sensitivity

```python
MIN_DUPE_NAME_SIMILARITY = 82   # Minimum name similarity % to group duplicates
MIN_DUPE_SIZE_RATIO = 0.3       # Downgrade HIGH confidence if sizes differ too much
MIN_ARCHIVE_PAIR_SIM = 82       # Archive vs extracted folder name match threshold
```

### Live-run approval

```python
ACTION_MODE = "ask"   # ask | section | item | auto
```

| Mode | Behavior |
| --- | --- |
| `ask` | Prompt at startup: section bulk, item-by-item, or auto |
| `section` | Approve each category bin (`a/`, `b/`, …) in bulk |
| `item` | Confirm every quarantine, duplicate stage, and move |
| `auto` | Run all actions; auto-stages only HIGH dupes with content MATCH |

### Investigation routing

```python
ROUTE_UNKNOWN_TENTATIVE_TO_INVESTIGATION = True
```

When enabled, weak vendor guesses (NFO scrape not in `vendor_db.py`) go to `_requiresinvestigation/_unverified_vendor` instead of creating random vendor folders.

---

## First run (dry run)

```powershell
$env:PYTHONUNBUFFERED=1
python main.py
```

Review outputs in `dedupe_reports/`:

1. **Run_Summary_*.txt** — high-level counts
2. **Restructure_Preview_*.md** — human-readable plan
3. **Investigation_Breakdown_*.csv** — why items need manual review
4. **Duplicate_Review_*.csv** — suspected duplicates

Reports are also copied to `{ROOT_DIR}/_dedupe_reports/` when the share is writable.

---

## Going live

1. Complete at least one full dry run and spot-check reports.
2. Set `DRY_RUN = False`.
3. Choose approval mode (`ACTION_MODE = "item"` recommended for first live run).
4. Run again and approve each phase:
   - Phase 1b: Quarantine (Mac/Linux-only)
   - Phase 2: Duplicate staging → `_delete-canidates`
   - Phase 3: Restructure moves
   - Phase 4: Empty directory purge

**Never skip reviewing `_delete-canidates`** — items are staged, not permanently deleted, but you should verify before removing that folder.

---

## Updating the vendor database

Edit `vendor_db.py`. Structure:

```python
VENDOR_DATABASE = {
    "Category_Name": {
        "Vendor Display Name": ["keyword1", "keyword2", "product name"],
    },
}
```

- First keyword in each list is the **strong** vendor-name match.
- After editing, bump `ENGINE_VERSION` or delete `dedupe_reports/scan_cache.json` to invalidate cached scans.

---

## .gitignore suggestion

```
dedupe_reports/
scan_cache.json
*.log
.venv/
__pycache__/
```

---

## Uninstall

Delete the project folder. Audiotheca does not install system services or registry entries. Any folders it created on your library (`_delete-canidates`, `_requiresinvestigation`, etc.) remain until you remove them manually.
