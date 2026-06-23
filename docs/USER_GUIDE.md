# Audiotheca — Quick User Guide

Engine **9.8.0** · Web UI **v0.2**

This guide gets you from zero to reviewing reports in the browser, then through staged live rollout on your library.

---

## What you need

| Tool | Required for | Install |
| --- | --- | --- |
| **Python 3.10+** | Engine + API | [python.org](https://www.python.org/downloads/) |
| **7-Zip** | Archive peek (`.rar`, `.7z`, `.iso`) | [7-zip.org](https://www.7-zip.org/) |
| **Node.js 20+** | Browser UI only | [nodejs.org](https://nodejs.org/) or `winget install OpenJS.NodeJS.LTS` |
| **Rust** | Tauri desktop app only | [rustup.rs](https://rustup.rs/) |

```powershell
cd "C:\path\to\audiotheca"   # quote paths with spaces
pip install -r requirements.txt
```

---

## Three ways to run

### 1. Engine only (CLI)

Scan and generate reports — no UI.

```powershell
cd "C:\Users\Cephyrix Zyth\Desktop\audiotheca"
$env:PYTHONUNBUFFERED=1
python main.py
```

CLI overrides (without editing `main.py`):

```powershell
python main.py --dry-run              # force dry run
python main.py --live                 # force live run
python main.py --root "Z:\_software\_audio"
```

Reports land in `dedupe_reports/` with a timestamp like `20260611_0208`.

### 2. Browser UI (recommended)

Dashboard for investigation, duplicates, restructure, archives, and live scan progress.

```powershell
cd "C:\Users\Cephyrix Zyth\Desktop\audiotheca"
.\start-ui.ps1
```

This opens the API in a second window and starts the UI at **http://localhost:5173**.

**API only** (no Node.js):

```powershell
.\start-api.ps1
# Health check: http://127.0.0.1:8787/api/health
```

**Manual two-terminal method:**

```powershell
# Terminal 1
python -m api.server

# Terminal 2
cd ui
npm install    # first time only
npm run dev
```

### 3. Desktop app (Tauri)

Native window; spawns API automatically. Requires Rust + Node.js.

```powershell
.\start-tauri.ps1
```

See [Tauri Build](TAURI_BUILD.md) for release installers and sidecars.

---

## Typical workflow

```
1. Dry run          → python main.py --dry-run   (or Scan tab in UI)
2. Review reports   → Browser UI or CSV files in dedupe_reports/
3. Fix vendors      → Edit vendor_db.py, re-run dry run
4. Stage 1 live     → Restructure + investigation routing (section approval)
5. Stage 2          → Scene renames (item approval)
6. Stage 3          → Archive cleanup (PowerShell script)
7. Stage 4          → Duplicate staging (optional)
```

Always review `Run_Summary_*.txt` before any live run.

---

## Web UI tabs

| Tab | What you do |
| --- | --- |
| **Dashboard** | Pick a run, see counts and quick stats |
| **Scan** | Start a dry-run from the UI; watch phase progress (WebSocket) |
| **Investigation** | Set vendor, reassign bucket, link parent, mark resolved, add vendor, export feedback |
| **Duplicates** | Pick keeper, mark bad matches, stage deletes, report manual dupes, export feedback CSV |
| **Restructure** | Preview vendor routes; open paths in Explorer |
| **Archives** | Archive peek verdicts; redundant archive size summary |
| **Scene renames** | Hash folder → product name proposals |

Decisions save to `dedupe_reports/decisions/approved_{stamp}.json`.

**Duplicates workflow:**
1. Pick **keeper** per group → **Save decisions**
2. **Bad match…** dropdown if the engine grouped wrong items (skipped on next scan)
3. **Preview deletes** then **Stage deletes** moves discards to `_delete-canidates`
4. **Report manual dupe** for pairs the engine missed
5. **Export feedback CSV** → `dedupe_reports/feedback/Duplicate_Feedback_Export_*.csv` for backend tuning

Engine reads `dedupe_reports/feedback/engine_hints.json` on each scan.

---

## Staged live rollout (current config)

`main.py` is set up for a **four-stage** rollout. Adjust before each stage.

| Stage | What runs | Key settings |
| --- | --- | --- |
| **1** (active) | Restructure + investigation routing | `DRY_RUN = False`, `ACTION_MODE = "section"`, `SCENE_AUTO_RENAME = False` |
| **2** | Scene-hash folder renames | `SCENE_AUTO_RENAME = True`, `ACTION_MODE = "item"` |
| **3** | Delete redundant archives | Run `move_redundant_archives_{stamp}.ps1` with `$Execute = $true` |
| **4** | Duplicate staging | Review `Duplicate_Review_*.csv`; use UI keeper export |

Generate archive delete script from a dry run:

```powershell
python gen_archive_delete_candidates.py dedupe_reports\Archive_Peek_20260611_0208.csv
```

Optional space tools (after dry run review):

```powershell
python space_recovery.py --help
```

---

## Key reports

| File | Use it for |
| --- | --- |
| `Run_Summary_*.txt` | Start here — counts and report index |
| `Investigation_Breakdown_*.csv` | Why items need manual review |
| `Duplicate_Review_*.csv` | Duplicate groups and confidence |
| `Restructure_Plan_*.csv` | Where items will move |
| `Archive_Peek_*.csv` | Archive vs extracted folder verdicts |
| `Scene_Rename_Plan_*.csv` | Proposed hash → product renames |
| `Multipart_Archive_Diagnostic_*.csv` | Incomplete multipart downloads |

Full reference: [Feature Guide](FEATURE_GUIDE.md).

---

## Safety rules

- **Dry run first** after any config or `vendor_db.py` change.
- **No permanent deletes** — duplicates go to `_delete-canidates`; you remove manually.
- **Backup** before Stage 1 live run.
- **Quote paths** with spaces: `"C:\Users\Cephyrix Zyth\Desktop\audiotheca"`.
- **One command per line** — do not paste `python -m api.server` and `cd ui` together.

---

## Common problems

| Problem | Fix |
| --- | --- |
| `npm: not recognized` | Install Node.js; close and reopen terminal |
| `Rust/Cargo not found` | Rust may be incomplete — see below; or use `.\start-ui.ps1` |
| `Set-Location: positional parameter...` | Quote the path: `cd "C:\Users\...\audiotheca"` |
| `No module named api.servercd` | Commands pasted together — run one line at a time |
| No terminal output for minutes | `$env:PYTHONUNBUFFERED=1` before `python main.py` |
| `NEEDS_7ZIP` in reports | Install 7-Zip; verify with `where.exe 7z` |

### Rust says installed but `cargo` not found

`rustup-init` may have run without finishing the download. Check:

```powershell
Test-Path "$env:USERPROFILE\.cargo\bin\cargo.exe"
```

If `False`, complete setup:

```powershell
& "$env:USERPROFILE\Downloads\rustup-init.exe" -y
```

Then **close and reopen** the terminal and run `.\start-tauri.ps1` again.

More: [FAQ](FAQ.md) · [Debug Runbook](DEBUG_RUNBOOK.md)

---

## Tests

```powershell
python -m pytest tests/ -q
```

---

## More documentation

| Guide | Contents |
| --- | --- |
| [Install Guide](INSTALL.md) | Full setup and configuration |
| [Feature Guide](FEATURE_GUIDE.md) | Phases, archive peek, reports |
| [FAQ](FAQ.md) | Common questions |
| [Debug Runbook](DEBUG_RUNBOOK.md) | Troubleshooting |
| [Tauri Build](TAURI_BUILD.md) | Desktop packaging |
| [Changelog](CHANGELOG.md) | Version history |
| [Backend Enhancement Roadmap](BACKEND_ENHANCEMENT_ROADMAP.md) | Per-module corrections & engine feedback plan |
