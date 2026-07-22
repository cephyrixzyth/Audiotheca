# Audiotheca — Debug Runbook

Use this runbook when a scan fails, produces unexpected results, or appears hung.

Engine version at time of writing: **10.0.0** · Web UI **1.0.12**

See also [main README](../README.md) troubleshooting table and [FAQ](FAQ.md).

---

## Quick diagnostics

Run these first and record outputs when reporting an issue.

```powershell
# 1. Version and config
python -c "import main; print(main.ENGINE_VERSION, main.ROOT_DIR, main.DRY_RUN)"

# 2. Share reachable?
Test-Path "Z:\_software\_audio"
Test-Path "Z:\_software\_audio" -PathType Container

# 3. Write access (live runs only)
# Should return True for live runs
python -c "import os; print(os.access(r'Z:\_software\_audio', os.W_OK))"

# 4. Optional deps
python -c "import pefile; import rapidfuzz; import tqdm; print('deps OK')"

# 5. Latest log tail
Get-Content ".\dedupe_engine.log" -Tail 40

# 6. Latest summary
Get-ChildItem ".\dedupe_reports\Run_Summary_*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content
```

---

## Symptom index

| Symptom | Jump to |
| --- | --- |
| Script exits immediately | [Startup failures](#startup-failures) |
| No output for 10+ minutes | [Silent / hung scan](#silent--hung-scan) |
| `Found 0 targets` | [Zero targets](#zero-targets) |
| Very high investigation count | [Investigation flood](#investigation-flood) |
| False duplicate groups | [False duplicates](#false-duplicates) |
| Missing duplicate pairs | [Missed duplicates](#missed-duplicates) |
| Move failed / permission errors | [Filesystem errors](#filesystem-errors) |
| Crash mid-run | [Interrupted runs](#interrupted-runs) |
| Stale / wrong results after code change | [Cache issues](#cache-issues) |
| Wrong vendor routing | [Vendor mis-identification](#vendor-mis-identification) |
| Scene hash unknown / huge | [Scene archive peek](#scene-archive-peek--multipart-diagnostic) |
| Archive vs folder — which to keep? | [Archive peek verdicts](#archive-peek-verdicts) |
| No phase ETA in terminal | [Progress / ETA](#progress--eta) |
| `npm` not recognized | [Web UI / API](#web-ui--api) |
| UI blank or cannot connect | [Web UI / API](#web-ui--api) |
| Scan from UI never starts | [Web UI / API](#web-ui--api) |

---

## Web UI / API

### `Rust/Cargo not found` (but Rust is "installed")

Usually one of these:

1. **Terminal opened before Rust install** — close and reopen PowerShell/Cursor terminal.
2. **PATH not refreshed** — `start-tauri.ps1` now reloads PATH from the registry and checks `%USERPROFILE%\.cargo\bin`.
3. **rustup started but toolchain never downloaded** — you may have only `~\.rustup\settings.toml` and **no** `~\.cargo\bin\cargo.exe`.

Verify:

```powershell
Test-Path "$env:USERPROFILE\.cargo\bin\cargo.exe"
cargo --version
```

If `False`, finish install (run in a **new** terminal as your user):

```powershell
# If you downloaded rustup-init.exe:
& "$env:USERPROFILE\Downloads\rustup-init.exe" -y

# Or via winget:
winget install Rustlang.Rustup
```

If download fails with `tcp connect error` / `os error 10013`, check firewall/VPN/antivirus blocking `static.rust-lang.org`, or install **Rust (MSVC)** from [rustup.rs](https://rustup.rs/) with admin rights.

**Workaround:** use browser UI — `.\start-ui.ps1` — no Rust required.

### `link.exe` not found / could not compile (MSVC)

Rust is installed but **Visual C++ Build Tools** are missing. Tauri cannot compile without `link.exe`.

```powershell
.\scripts\install_msvc_prereqs.ps1
# or: winget install Microsoft.VisualStudio.2022.BuildTools
```

In the installer, enable **Desktop development with C++** (MSVC v143). Restart terminal after install.

Verify: `where.exe link`

**Workaround:** `.\start-ui.ps1` — same UI in the browser, no MSVC needed.

### `Could not connect to index.crates.io`

Firewall/VPN/antivirus blocking Cargo downloads. Retry on a stable network, or temporarily disable VPN. First successful build caches crates locally.

### `npm: not recognized`

Node.js is missing. Install via [nodejs.org](https://nodejs.org/) or `winget install OpenJS.NodeJS.LTS`, then restart the terminal. Use `.\start-api.ps1` for API-only mode.

### `Set-Location: positional parameter...`

Path contains spaces without quotes:

```powershell
cd "C:\Users\Cephyrix Zyth\Desktop\audiotheca"
```

### `No module named api.servercd` or `api.servernpm`

Commands were pasted on one line. Run **one command per line**:

```powershell
python -m api.server
```

### UI loads but shows no runs

1. Confirm reports exist: `Get-ChildItem dedupe_reports\Run_Summary_*.txt`
2. API health: `Invoke-RestMethod http://127.0.0.1:8787/api/health`
3. Run a dry scan if folder is empty: `python main.py --dry-run`

### Scan from UI hangs or fails

- Map network drive (`Z:`) before starting API
- Check job status: `GET http://127.0.0.1:8787/api/jobs` (requires auth)
- Engine log: `dedupe_engine.log`
- WebSocket events need a scoped ticket: `ws://127.0.0.1:8787/api/jobs/{id}/events?ticket=…`
  (issue via `POST /api/auth/ticket` with `scope=/api/jobs/{id}/events`; see [Security](SECURITY.md))

### UI 401 / auth loops

- Local: confirm API is on `127.0.0.1` and `/api/auth/token` or `/api/auth/session` succeeds
- Docker/Unraid: confirm `AUDIOTHECA_PROXY_SECRET` matches on API + UI nginx; bootstrap stays disabled
- After API container restart, reload the UI so it can mint a fresh opaque session cookie

### Open in Explorer does nothing

Requires Windows and a valid local/mapped path. Network UNC paths may need to be mapped to a drive letter first.

---

## Startup failures

### `Cannot reach network share`

```
[X] ERROR: Cannot reach network share.
```

**Cause:** `ROOT_DIR` path doesn't exist or drive not mapped.

**Fix:**
1. Verify drive letter in Explorer
2. Re-map network drive before running
3. Confirm `ROOT_DIR` in `main.py` matches actual path (no trailing typos)

### `Drive is read-only`

**Cause:** Live run on read-only share.

**Fix:** Use `DRY_RUN = True`, or remount share with write access.

### `ModuleNotFoundError: vendor_db`

**Cause:** Running from wrong directory.

**Fix:** Run from project root where `vendor_db.py` sits beside `main.py`.

---

## Silent / hung scan

### No terminal output during Phase 1

**Cause:** Python stdout buffering + long network enumeration.

**Fix:**

```powershell
$env:PYTHONUNBUFFERED=1
python main.py
```

**Verify progress:**

```powershell
# Log should update within minutes
Get-Content ".\dedupe_engine.log" -Wait -Tail 20

# Cache file grows as items complete
Get-Item ".\dedupe_reports\scan_cache.json" -ErrorAction SilentlyContinue
```

**If truly stuck (>20 min, no log growth):**
1. Reduce `MAX_WORKERS` to 2
2. Reduce `MAX_WALK_DEPTH` to 5 temporarily
3. Set `ROOT_DIR` to a single small bin to isolate
4. Check for one path causing SMB hang (see [Isolate a bad path](#isolate-a-bad-path))

---

## Zero targets

### `WARNING: Found 0 targets`

**Cause:** Root empty, wrong path, or everything is in `IGNORE_BINS`.

**Check:**
- Items must be direct children of category bins (not nested under `_requiresinvestigation`)
- Folders starting with `_` are skipped
- Root must contain section folders (`a`, `b`, etc.), not only special bins

---

## Investigation flood

### 40%+ items in investigation

**Expected** on libraries with many scene hash releases and unlabeled sample packs.

**Triage workflow:**

1. Open `Investigation_Breakdown_*.csv`
2. Sort by **Investigation Bucket**
3. Address highest-volume buckets first:

| Bucket | Action |
| --- | --- |
| `_scene_release_id` | Flatten/rename wrappers; inner product may identify cleanly |
| `_library_internal` | Fix target discovery — don't scan subfolders as top-level items |
| `_likely_component` | Merge into parent product identified in Reason column |
| `_unknown_vendor` | Add keywords to `vendor_db.py` |
| `_unverified_vendor` | Add vendor to database or confirm NFO scrape is wrong |

**Temporary relief:** Set `ROUTE_UNKNOWN_TENTATIVE_TO_INVESTIGATION = False` only if you accept random vendor folder names from bad NFO scrapes.

---

## False duplicates

### Unrelated products grouped together

**Check Duplicate_Review CSV columns:**
- Same **Vendor**?
- Same **Fingerprint**?
- **Name Similarity %** ≥ 82?
- **Content Check** = MATCH or SKIPPED?

**Common causes:**

| Pattern | Fix |
| --- | --- |
| Generic fingerprint (`documentation`, `license`) | Already in `GENERIC_BASE_NAMES` — bump engine if new generic term appears |
| Wrong vendor from keyword collision | Add keyword to `KEYWORD_BLOCKLIST` in `main.py` |
| KONTAKT library exploded | Verify `LIBRARY_INTERNAL_DIRS` guard in `is_vendor_grouping()` |

**Debug one group manually:**

```python
from main import DeduplicationEngine
e = DeduplicationEngine(r"Z:\_software\_audio")
# Compare fingerprints
print(e.get_version_and_base("Some Folder Name", "Vendor Name"))
```

---

## Missed duplicates

### Obvious duplicate not in report

**Check:**
1. Different vendors assigned → won't group (by design)
2. Different fingerprints after tag stripping
3. Confidence LOW → filtered from review
4. One item in investigation, one routed — different pipelines
5. Archive + folder pair may be in **Archive Coexistence** CSV instead of Duplicate Review

**Lower thresholds (carefully):**

```python
MIN_DUPE_NAME_SIMILARITY = 78   # default 82
MIN_ARCHIVE_PAIR_SIM = 78
```

Re dry-run and check false positive rate.

---

## Filesystem errors

### `move_and_merge failed` / `safe_move failed` in log

**Common causes:**
- Destination already exists (merge collision)
- Path too long (Windows MAX_PATH)
- File open in another program
- Network drop mid-move
- Insufficient permissions

**Response:**
1. Note path from log line
2. Check if partial move occurred
3. Do **not** re-run live until state is verified
4. Use `_audit_info.json` and Organization Log CSV to trace

### Long path errors

**Fix:** Enable Windows long paths, or shorten intermediate folder names before live run.

---

## Interrupted runs

### Ctrl+C during scan

Engine catches `KeyboardInterrupt`, saves partial reports and cache in `finally` block.

**After interrupt:**
1. Check `dedupe_reports/` for partial timestamp
2. Review log for last completed item
3. Safe to re-run — cache skips unchanged paths

### Exception mid-run

```
[X] Run aborted: ... — writing partial reports.
```

**Fix:** Read full traceback in log (`exc_info=True`). Partial reports still written.

---

## Cache issues

### Results don't reflect code changes

**Fix:**

```powershell
Remove-Item ".\dedupe_reports\scan_cache.json" -ErrorAction SilentlyContinue
```

Also bump `ENGINE_VERSION` in `main.py` when changing scan logic.

### Cache corruption suspicion

Symptoms: impossible sizes, missing nested data.

**Fix:** Delete `scan_cache.json` and full re-scan.

---

## Vendor mis-identification

### Wrong vendor folder

1. Check **ID Method** column in Restructure CSV
2. `NAME_PRODUCT` weak keyword → add to `KEYWORD_BLOCKLIST` or reorder routes
3. `NFO` bad scrape → verify NFO length cap; item should land in `_unverified_vendor`
4. `RECONCILED` wrong → check vendor conflicts in preview MD

**Test keyword matching:**

```python
from main import DeduplicationEngine
e = DeduplicationEngine(".")
print(e._match_vendor_detailed("Klevgrand Hillman 1.0.3"))
```

---

## Progress / ETA

9.7+ prints per-phase progress:

```
▶ Phase 1b — Parallel scan
  1,204 / 7,204 item  (17%)  ·  elapsed 12m30s  ·  ETA 58m12s
```

If ETA is missing:

1. Set `$env:PYTHONUNBUFFERED=1`
2. Install `tqdm` for Phase 1b bar: `pip install tqdm`
3. Watch `dedupe_engine.log` — phases log at INFO

---

## Scene archive peek & multipart diagnostic

### Hash folder still `_scene_release_id` after scan

1. Open `Scene_Archive_Peek_*.csv` — column `inferred_product`
2. Open `Multipart_Archive_Diagnostic_*.csv` for the same `folder_path`

| Diagnosis | Action |
| --- | --- |
| `MISSING_PART01` | Incomplete multipart download — re-fetch part01 or full set (common on `287901`) |
| `GAP_IN_SEQUENCE` | Missing intermediate `.partN.rar` files |
| `CORRUPT_OR_UNREADABLE_PART01` | part01 present but 7-Zip cannot open — re-download |
| `OK` + inferred name | Enable `SCENE_AUTO_RENAME` or rename manually from CSV |

### Diagnose one folder manually

```powershell
python -c "
from pathlib import Path
from archive_peek import diagnose_multipart_folder, find_7z, peek_archive
folder = Path(r'Z:\_software\_audio\=\287901\287901')
print(diagnose_multipart_folder(folder, find_7z()))
parts = sorted(folder.glob('*.part*.rar'))
if parts:
    print(peek_archive(parts[0], find_7z(), limit=8))
"
```

### 7-Zip not found

Install [7-Zip](https://www.7-zip.org/) or Scoop: `scoop install 7zip`. Verify:

```powershell
python -c "from archive_peek import find_7z; print(find_7z())"
```

---

## Archive peek verdicts

After dry run, open `Archive_Peek_*.csv`:

| Verdict | Action |
| --- | --- |
| `MATCHES_EXTRACTED_FOLDER` | Safe to delete archive after spot-check |
| `LOOKS_LIKE_PRODUCT` | Archive is installer; keep extracted folder if present |
| `MULTIPART_SECONDARY` | Informational — part1 row has the real listing |
| `LIST_FAILED` | See multipart diagnostic; often missing part01 |

Re-peek without full scan:

```powershell
python peek_archives.py
```

---

## Isolate a bad path

When one folder hangs SMB:

1. Set `ROOT_DIR` to parent bin containing suspect item
2. Set `MAX_WORKERS = 1`
3. Temporarily comment out other bins in a test copy, or add early-exit debug

Watch log for last path before stall:

```powershell
Select-String -Path ".\dedupe_engine.log" -Pattern "Scan failed|Worker failed" | Select-Object -Last 20
```

---

## Log levels & verbose debugging

Default log: `dedupe_engine.log` (INFO).

For deeper debugging, temporarily change in `_setup_logging`:

```python
level=logging.DEBUG,
```

Revert after diagnosis — DEBUG on large libraries produces huge logs on network shares.

---

## Pre-live-run checklist

```
[ ] ENGINE_VERSION correct in output header
[ ] DRY_RUN = True completed successfully
[ ] Run_Summary counts plausible vs prior run
[ ] Investigation_Breakdown reviewed by bucket
[ ] Duplicate_Review HIGH groups spot-checked (5–10 samples)
[ ] Nested_Folder_Issues reviewed for data-loss risk
[ ] Backup or snapshot of library exists
[ ] ACTION_MODE set (item recommended for first live)
[ ] PYTHONUNBUFFERED=1 set
[ ] 7-Zip available (`find_7z()` prints path at run start)
[ ] Archive_Peek + Scene_Archive_Peek reviewed
[ ] Multipart_Archive_Diagnostic checked for MISSING_PART01
[ ] Share writable (live only)
```

---

## Post-live-run verification

```powershell
# Organization log actions
Import-Csv ".\dedupe_reports\Library_Organization_Log_*.csv" | Group-Object Action

# Failed moves
Select-String -Path ".\dedupe_engine.log" -Pattern "FAILED|failed|ERROR"

# Staged dupes count
(Get-ChildItem "Z:\_software\_audio\_delete-canidates" -ErrorAction SilentlyContinue).Count

# Investigation bucket counts
Import-Csv ".\dedupe_reports\Investigation_Breakdown_*.csv" | Group-Object "Investigation Bucket"
```

---

## Escalation template

When asking for help, include:

```
ENGINE_VERSION:
ROOT_DIR:
DRY_RUN:
MAX_WALK_DEPTH / PROBE_DEPTH / MAX_WORKERS:
Symptom:
Last 20 log lines:
Run_Summary counts:
Example item path that misbehaves:
Expected vs actual behavior:
```

---

## Recovery procedures

### Restore from staged deletes

Items in `_delete-canidates` are full folder trees. Move back to original location using paths from Duplicate Review CSV or `_audit_info.json`.

### Undo restructure moves

Each destination folder may contain `_audit_info.json`:

```json
{
  "original_path": "Z:\\_software\\_audio\\a\\Old Location\\Product",
  ...
}
```

Move folder back manually. Organization Log CSV lists every action.

### Nuclear reset of Audiotheca folders

Only if you understand what's in each:

```
_requiresinvestigation/
_delete-canidates/
_non_pc_quarantine/
_dedupe_reports/
```

Do **not** delete `_tonex libraries` without review — it may contain intentionally organized content.
