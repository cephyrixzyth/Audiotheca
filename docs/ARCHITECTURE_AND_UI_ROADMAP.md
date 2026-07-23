# Audiotheca — Architecture & UI Roadmap

How Audiotheca evolved from a CLI script into a desktop product. **v10.0.0** ships the scan engine plus a **Web UI 1.0** (FastAPI + React) and **Tauri 2** desktop shell with PyInstaller sidecars. The UI consumes existing CSV/JSON report contracts — it does not reimplement peek or matching logic.

**Shipped (UI 1.0.12 / engine 10.0):** Everything in 1.0.5 plus API **domain routers** (`api/routers/`), short-lived **access tickets**, logical **path keys** across feedback stores, stamp-scoped scene/archive overrides, dedupe **VERSION_COEXIST**, Vitest + Playwright smoke tests, and Tauri startup hardening (no aggressive port killing).

**Roadmap complete:** SQLite job store, archive diff wizard, reference dedupe, feedback exports, and spec waves A–R are implemented. Optional future work: native chromaprint, live Gluetun routing, full JUCE DAW plugin build.

See the [main README](../README.md) for current tab list and [Feature Guide](FEATURE_GUIDE.md) for phase details.

---

## Should you rewrite in another language?

**Recommendation: no full rewrite yet.** Modularize the Python engine, expose a stable API, then add a native UI shell.

| Approach | Verdict |
| --- | --- |
| **Python core + Tauri/React UI** | Best starting point — reuse v9.7.0 engine (incl. archive peek API), ship faster |
| **Python FastAPI + web UI** | Good if you want browser-based or remote access to network shares |
| **Full Rust/Go rewrite** | Only after API + UI workflows are proven |
| **Rust/Go helper binaries** | Best performance win without throwing away matching logic |

### Why keep Python for the engine (for now)

- Vendor matching, reconciliation, and investigation buckets are already tuned for your library
- Regex and `vendor_db.py` change frequently — Python iteration speed matters more than scan microseconds
- On SMB shares, **network latency dominates**; rewriting walkers in Rust often saves less than 20–30%
- A UI needs **stable JSON/SQLite contracts**, not a new language

### When to add Rust or Go

Extract **hot paths only** as CLI helpers (like `fpcalc` for Acoustid):

| Module | Reference | Purpose |
| --- | --- | --- |
| Rolling hash | [klauspost/dedup](https://github.com/klauspost/dedup) | Full-file dedupe at GB scale |
| Parallel walk | [jpillora/dedup](https://github.com/jpillora/dedup) | Cancelable directory traversal |
| Archive list/extract | 7-Zip backend | `.rar`/`.7z`/`.iso` without Python pain |

Call from Python via subprocess; swap implementations without touching UI or planning logic.

---

## Target architecture

```
┌──────────────────────────────────────────────────────────────┐
│  UI — Tauri 2 + React + TypeScript                           │
│  Tree · diff · duplicate cards · investigation inbox         │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTP + WebSocket (localhost)
┌────────────────────────────▼─────────────────────────────────┐
│  Audiotheca API — FastAPI (Python)                             │
│  Jobs · progress events · approve · execute                  │
└────────────────────────────┬─────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│  Engine — audiotheca package (extracted from main.py)        │
│  scan · identify · dedupe · plan · execute                   │
└────────────────────────────┬─────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────┐
│  SQLite (jobs/items/actions) + scan_cache.json + reports     │
└──────────────────────────────────────────────────────────────┘
```

---

## Phase 0 — Package split (do this before UI)

Refactor without behavior changes:

```
audiotheca/
├── audiotheca/
│   ├── config.py
│   ├── engine.py
│   ├── scan.py
│   ├── identify.py
│   ├── dedupe.py
│   ├── plan.py
│   ├── execute.py
│   ├── reports.py
│   └── models.py          # dataclasses or Pydantic
├── vendor_db.py
├── cli.py                 # audiotheca scan | report | execute
└── api/
    ├── server.py          # FastAPI app factory + middleware
    ├── deps.py            # Shared router dependencies
    └── routers/           # Domain route modules (runs, jobs, browse, …)
```

CLI subcommands map to today's phases:

```bash
audiotheca scan --root Z:\_software\_audio --dry-run
audiotheca report --job latest --open investigation
audiotheca execute --job latest --plan approved.json
```

---

## Phase 1 — Job model + API (4–6 weeks)

### Job lifecycle

```
CREATED → SCANNING → RECONCILING → PLANNING → AWAITING_APPROVAL → EXECUTING → DONE
```

### SQLite tables

| Table | Contents |
| --- | --- |
| `jobs` | root_dir, config, status, timestamps, engine_version |
| `items` | path, vendor, fingerprint, size, bucket, id_method |
| `duplicate_groups` | key, confidence, group_kind, content_check |
| `duplicate_members` | group_id, item_id, recommendation |
| `actions` | type, src, dst, approved, executed, error |
| `coexistence` | archive path, folder path, similarity |

### API surface

| Endpoint | Purpose |
| --- | --- |
| `POST /jobs` | Start async scan |
| `GET /jobs/{id}` | Progress + stats |
| `GET /jobs/{id}/items?section=a&bucket=_unknown_vendor` | Filtered inventory |
| `GET /jobs/{id}/duplicates` | Groups for review UI |
| `PATCH /jobs/{id}/duplicates/{gid}` | Set keeper, stage others |
| `POST /jobs/{id}/approve` | Approve actions (section/item/all) |
| `POST /jobs/{id}/execute` | Run approved actions only |
| `WS /jobs/{id}/events` | `{phase, current, total, path}` stream |

### Patterns to borrow

| Source | Pattern |
| --- | --- |
| [dedupe.io blocking](https://docs.dedupe.io/en/latest/how-it-works/Making-smart-comparisons.html) | Predicate blocks before pairwise compare |
| [dedupe.io active learning](https://docs.dedupe.io/en/latest/API-documentation.html) | Store user keep/skip labels per job for future runs |
| [soundaudit](https://pypi.org/project/soundaudit/) | Separate **scan** from **analyze** passes; hash tiers |
| [MusicDeduplicator](https://github.com/JameZUK/MusicDeduplicator) | Metadata block first, fingerprint confirm second |

**Next sources (not yet implemented):** BaseHead, Sononym, ADSR Sample Manager, Essentia, mutagen, ssdeep/TLSH, RF64, BS.1770 — full inventory in [SOURCES.md](SOURCES.md); backlog in [ROADMAP_REMAINING.md Phase M](ROADMAP_REMAINING.md#phase-m--external-sources-build-out).

---

## Phase 2 — Desktop UI (8–12 weeks)

**Stack: Tauri 2 + React + TypeScript**

Why Tauri over Electron: smaller binary, native Windows paths, Rust sidecar for future hash/extract helpers.

Why not pure web first: your library is on `Z:\` — a local desktop app avoids browser sandbox path issues.

### Screen map (one screen per report you already have)

| Screen | Engine data | UX reference |
| --- | --- | --- |
| **Dashboard** | Run summary | CI dashboard — KPI cards |
| **Library explorer** | Items + tree | VS Code sidebar + [Double Commander](https://doublecmd.sourceforge.io/) dual pane |
| **Restructure** | Restructure plan | Git staging — before → after |
| **Duplicate review** | Duplicate groups | dedupe.io pairwise cards |
| **Investigation inbox** | Investigation buckets | Email filters — triage by bucket |
| **Coexistence** | Archive pairs | Sync conflict resolver |
| **Nested issues** | Nested CSV | Linter panel with fix hints |
| **Approval queue** | Pending actions | PR review — bulk + item mode |
| **Execution log** | Organization log | Build output — filter FAILED |

### MVP UI (build this first — 2–3 weeks after Phase 1)

**Report Viewer + Investigation Inbox only:**

1. Load job from SQLite (or import latest CSV bundle)
2. Tabs: Investigation | Duplicates | Restructure
3. Search/filter by section, vendor, bucket
4. Mark decisions → export `approved.json`
5. CLI executes: `audiotheca execute --plan approved.json`

No live moves from UI until decisions feel right.

### Essential interactions

- **Dry-run banner** until user toggles live mode
- **Path diff row:** `current → planned` with vendor badge + ID confidence
- **Duplicate card:** members, size ratio, content check, pick keeper (keyboard y/n)
- **Investigation triage:** reassign bucket, link to suggested parent product
- **Open in Explorer** on any path
- **Section bulk approve** + **item mode** (matches `ACTION_MODE`)

---

## Phase 3 — Archive extraction & compare

Coexistence findings (`ARCHIVE_EXTRACTED_SIBLING`, cross-item pairs) need tooling, not just reports.

### Extraction backends

| Format | Backend |
| --- | --- |
| `.zip` | Python `zipfile` |
| `.7z` | `7z` CLI or `py7zr` |
| `.rar` | `7z` CLI (check UnRAR license for distribution) |
| `.iso` | 7z or Windows mount |

### UI actions per coexistence row

| Action | Behavior |
| --- | --- |
| Keep archive | Stage extracted folder → `_delete-canidates` |
| Keep extracted | Stage archive → `_delete-canidates` |
| Extract & compare | Extract to `_extract_preview/{job_id}/`, run sparse hash vs folder |
| Open archive listing | Tree of contents without full extract (7z `l`) |

Never auto-delete both — same safety model as today.

---

## Phase 4 — Advanced features (backlog)

| Feature | Inspiration | Priority |
| --- | --- | --- |
| Size-bucket blocking | dedupe.io | High |
| Parent link for `_likely_component` | Custom | High |
| Full hash &lt; 200 MB | soundaudit, klauspost/dedup | Medium |
| Audio fingerprint WAV/FLAC | MusicDeduplicator / AcoustID | Medium |
| UCS category hints | [Universal Category System](https://universalcategorysystem.com/) | Medium |
| Soundminer-style metadata fields | Soundminer | Low |
| Incremental scan (skip unchanged sections) | soundaudit | Medium |

---

## Language summary

| Layer | Choice | Why |
| --- | --- | --- |
| Engine | Python 3.11+ | Current code, pefile, rapidfuzz |
| API | Python FastAPI | Same repo, async jobs, WebSocket |
| UI | TypeScript + Tauri 2 | Rich desktop, best for detailed UI |
| Native helpers | Rust (optional) | Hash/extract performance later |

---

## Decision log

| Decision | Choice |
| --- | --- |
| Full rewrite now? | **No** |
| UI framework | **Tauri 2 + React** |
| Persistence | **SQLite + existing CSV reports** |
| First UI screen | **Investigation inbox** |
| Archive tools | **Phase 3 — 7z CLI** |
| SMB strategy | Keep depth limits; expose worker count in UI |

---

## Next steps (ordered)

1. ~~Git init + docs~~ ✓
2. ~~FastAPI + WebSocket progress~~ ✓ (v1.0)
3. ~~React report viewer + investigation inbox~~ ✓
4. ~~Duplicate review + keeper export~~ ✓
5. ~~Tauri shell + PyInstaller sidecars~~ ✓
6. ~~Wire `approved.json` into engine execute step~~ ✓
7. ~~Split `main.py` → `audiotheca/` package + `cli.py`~~ ✓
8. ~~SQLite schema + import from scan results~~ ✓
9. ~~Live execute from UI (section/item approval)~~ ✓
10. ~~Archive extract + compare wizard~~ ✓

Optional follow-ups: native chromaprint packaging in release CI, live Gluetun routing polish, full JUCE DAW plugin build.