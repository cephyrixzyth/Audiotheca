# Audiotheca — Architecture & UI Roadmap

This document describes how to evolve Audiotheca from a CLI script into a product with a detailed UI, optional archive extraction, and patterns borrowed from dedupe tools, file managers, and asset librarians (Soundminer, soundaudit, dedupe.io).

---

## Should you rewrite in another language?

**Recommendation: no full rewrite yet.** Keep the Python engine as the core and add a proper boundary around it.

| Approach | Verdict |
| --- | --- |
| **Python core + modern UI shell** | Best starting point — reuse v9.6.0 logic, ship faster |
| **Full Rust/Go rewrite** | Only after the API and UI workflows are proven |
| **Electron/Tauri + Python sidecar** | Good for rich desktop UI on Windows + network paths |

### Why keep Python for the engine (for now)

- Matching, reconciliation, and reporting logic is already battle-tested on SMB shares
- `pefile`, `rapidfuzz`, and rapid iteration on regex/vendor rules matter more than raw scan speed
- Network I/O dominates runtime — a Rust rewrite rarely cuts total scan time in half
- A UI needs **stable contracts** (JSON/CSV/SQLite), not a new language

### When to extract hot paths to Rust/Go

Consider a native helper later for:

- Full-file hashing at scale (klauspost/dedup-style rolling hash)
- Parallel directory walking with cancel tokens
- Archive listing/extraction (7z/rar backends)

Expose these as CLI binaries or DLLs called from Python — same pattern as `fpcalc` for Acoustid.

---

## Target architecture

```
┌─────────────────────────────────────────────────────────────┐
│  UI Layer (Phase 2+)                                        │
│  Tauri 2 / React OR Electron — file tree, diff, approvals │
└───────────────────────────┬─────────────────────────────────┘
                            │ IPC: REST / gRPC / stdin JSON
┌───────────────────────────▼─────────────────────────────────┐
│  Audiotheca API (Phase 1)                                   │
│  FastAPI or CLI subcommands — jobs, progress, reports       │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  Engine Core (Python — extract from main.py)                  │
│  scan · identify · dedupe · plan · execute                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  Storage: SQLite job DB + report artifacts + scan cache       │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 0 — Repo hygiene (done)

- [x] Git repo with docs
- [ ] Split `main.py` into modules (next step before UI)

Suggested package layout:

```
audiotheca/
├── audiotheca/
│   ├── __init__.py
│   ├── config.py
│   ├── engine.py          # DeduplicationEngine
│   ├── scan.py
│   ├── identify.py
│   ├── dedupe.py
│   ├── plan.py
│   ├── execute.py
│   ├── reports.py
│   └── models.py          # dataclasses / pydantic
├── vendor_db.py
├── cli.py                 # python -m audiotheca
└── api/                   # Phase 1
    └── server.py
```

---

## Phase 1 — Headless API + job model (4–6 weeks)

**Goal:** UI can drive the engine without rewriting business logic.

### Job lifecycle

```
CREATED → SCANNING → RECONCILING → PLANNING → AWAITING_APPROVAL → EXECUTING → COMPLETE
                                                      ↓
                                                  CANCELLED / FAILED
```

Persist in **SQLite**:

- `jobs` — id, root_dir, dry_run, config snapshot, status, timestamps
- `items` — path, vendor, fingerprint, size, os_status, investigation_bucket
- `duplicate_groups` — members, confidence, content_check, user decision
- `actions` — planned move/quarantine/stage/extract, approved, executed, error

### API endpoints (FastAPI example)

| Endpoint | Purpose |
| --- | --- |
| `POST /jobs` | Start scan (async background task) |
| `GET /jobs/{id}` | Status + progress counters |
| `GET /jobs/{id}/items` | Paginated inventory with filters |
| `GET /jobs/{id}/duplicates` | Duplicate groups for review UI |
| `GET /jobs/{id}/investigation` | Bucket breakdown |
| `POST /jobs/{id}/approve` | Batch approve actions by section/item/id |
| `POST /jobs/{id}/execute` | Run approved actions only |
| `WS /jobs/{id}/events` | Progress stream (replace silent CLI) |

### Patterns to borrow

| Source | Pattern |
| --- | --- |
| [dedupe.io](https://docs.dedupe.io/en/latest/how-it-works/Making-smart-comparisons.html) | Blocking keys before pairwise compare; active-learning labels stored per job |
| [soundaudit](https://pypi.org/project/soundaudit/) | Incremental scan, analyze passes separate from scan, JSON/CSV/MD export |
| [jpillora/dedup](https://github.com/jpillora/dedup) | Hash strategy tiers (head / head-tail / full) as user-selectable per job |

---

## Phase 2 — Desktop UI shell (8–12 weeks)

**Recommended stack:** **Tauri 2 + React + TypeScript**

- Smaller footprint than Electron
- Native file dialogs and path handling on Windows
- React ecosystem for complex tables (TanStack Table), trees (react-arborist), diff views

**Alternative:** Electron if you want maximum npm library compatibility with minimal Rust.

### UI modules (map to your reports)

| Screen | Data source | Reference UX |
| --- | --- | --- |
| **Dashboard** | Run summary | CI dashboard — counts, cache hits, errors |
| **Library tree** | Items + planned destinations | VS Code sidebar / Double Commander pane |
| **Restructure preview** | Restructure plan | Git staging view — before/after path |
| **Duplicate review** | Duplicate groups | dedupe.io pairwise review — side-by-side cards |
| **Investigation inbox** | Investigation buckets | Email inbox — filter by bucket, bulk actions |
| **Coexistence** | Archive pairs | Sync tool — archive vs folder comparison |
| **Nested issues** | Nested CSV | Lint panel — fix suggestions |
| **Approval queue** | Pending actions | PR review — approve section / item / all |
| **Execution log** | Organization log | Build log with filter by FAILED |

### Essential interactions

1. **Dry run default** — big banner until user explicitly enables live mode
2. **Diff preview** — show `current_path → destination` with vendor/confidence badges
3. **Duplicate group card** — list members, sparse hash result, pick keeper, stage others
4. **Investigation triage** — drag item to bucket or merge into suggested parent
5. **Section bulk approve** — matches current `ACTION_MODE = section`
6. **Item-by-item mode** — keyboard shortcuts (y/n/s) for fast review

---

## Phase 3 — Archive extraction & format tools

Many coexistence findings are **archive + extracted folder** pairs. Add optional extraction pipeline:

### Extraction service

| Format | Backend |
| --- | --- |
| `.zip` | Python `zipfile` or native |
| `.7z` | `7z` CLI or `py7zr` |
| `.rar` | `unrar` / `7z` CLI (license-aware) |
| `.iso` | 7z or Windows mount helper |

**UI flow:**

1. Coexistence row shows archive + extracted sibling
2. Actions: **Keep archive only** | **Keep extracted only** | **Extract to temp & compare** | **Stage one to `_delete-canidates`**
3. Never auto-delete both — mirror current safety model

### Compare-after-extract

- Extract archive to `{ROOT}/_extract_preview/{job_id}/` (ignored bin)
- Run sparse hash on largest files vs existing folder
- Show MATCH/DIFFERS in UI before user picks keeper

---

## Phase 4 — Advanced dedupe (optional)

| Feature | Source inspiration | Effort |
| --- | --- | --- |
| Size-bucket blocking | dedupe.io predicate blocks | Low |
| Full hash for files &lt; 200 MB | klauspost/dedup, soundaudit | Medium |
| Audio fingerprint (WAV/FLAC) | MusicDeduplicator / AcoustID | High |
| UCS category hints | [UCS](https://universalcategorysystem.com/) | Medium |
| Soundminer-style sidecar | Soundminer metadata fields | Medium |
| Parent linking for `_likely_component` | Custom — merge-into suggestion | Low |

---

## Language choice summary

| Layer | Language | Reason |
| --- | --- | --- |
| Engine | **Python 3.11+** | Existing logic, regex, pefile |
| API | **Python (FastAPI)** | Same codebase, async jobs |
| UI | **TypeScript (Tauri/React)** | Rich desktop, best for detailed UI |
| Hash/extract native | **Rust or Go** (later) | Optional performance module |

---

## Recommended first UI milestone (MVP)

**"Report Viewer + Approval" — 2–3 weeks after Phase 1 API**

1. Load latest job SQLite / CSV exports
2. Three tabs: **Restructure** | **Duplicates** | **Investigation**
3. Filter/search by section, vendor, bucket
4. Export approved action list JSON
5. CLI executes approved list (`audiotheca execute --plan approved.json`)

No file moves from UI yet — validates workflows before wiring execution.

---

## Second UI milestone

**"Live job runner"**

1. Start scan from UI (pick `ROOT_DIR`)
2. WebSocket progress bar (items/sec, cache hits, current path)
3. Inline duplicate keeper selection
4. Execute approved actions with rollback log

---

## Third UI milestone

**"Archive & explorer"**

1. Tree view of one release folder (depth-limited)
2. Extract archive preview
3. Coexistence resolution wizard
4. Open in Explorer / copy path

---

## References to study

| Project | URL | Takeaway |
| --- | --- | --- |
| dedupe.io | https://docs.dedupe.io/ | Blocking, pairwise review, training labels |
| soundaudit | https://pypi.org/project/soundaudit/ | Scan/analyze split, hash tiers, TUI |
| MusicDeduplicator | https://github.com/JameZUK/MusicDeduplicator | Metadata block + fingerprint confirm |
| klauspost/dedup | https://github.com/klauspost/dedup | Fast rolling hash |
| Double Commander | https://doublecmd.sourceforge.io/ | Dual-pane file manager UX |
| Files (Google) | Material file browser patterns | Tree + detail panel |
| Universal Category System | https://universalcategorysystem.com/ | Sample library taxonomy |
| Tauri | https://v2.tauri.app/ | Desktop shell recommendation |

---

## Decision log (suggested defaults)

| Decision | Choice |
| --- | --- |
| Rewrite engine now? | **No** — modularize Python first |
| UI framework | **Tauri 2 + React** |
| Job storage | **SQLite** |
| First feature | **Report viewer + investigation inbox** |
| Archive extraction | **Phase 3** — 7z CLI backend |
| Network share strategy | Keep depth limits + cache; expose worker count in UI |

---

## Next concrete steps

1. `git init` + initial commit (docs + engine)
2. Refactor `main.py` → `audiotheca/` package (no behavior change)
3. Add `cli.py` with subcommands: `scan`, `report`, `execute`
4. Add SQLite schema + import from CSV reports
5. Scaffold Tauri app reading SQLite from job folder
6. Build Investigation Inbox as first screen
