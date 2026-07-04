# Audiotheca — Phased Roadmap (2026-07)

Concrete build order after v10 / Web UI v0.2. Each phase lists **what exists today**, **what we add**, and **how it maps to reports + API**.

---

## Which facet matters most?

| Priority | Facet | Why |
| --- | --- | --- |
| **P0 — now** | **Scan reliability & honest progress** | A NAS Phase 1a can sit on `iterdir()` for an hour with a frozen “ETA ~6m”. Without trust in live progress, every other tab is secondary. |
| **P1 — next product win** | **Archive diff wizard** | You already ship `Archive_Peek_*.csv`, `Archive_Coexistence_*.csv`, `/api/archive/list`, archive peek feedback + execute, and Explorer dual-pane. The gap is a guided **archive ↔ folder diff** — not new engine logic. |
| **P2** | Reference-directory dedupe (dupeGuru-style) | High value for “canonical tree vs messy library”, but needs new scan mode + UI; duplicates tab only covers in-root groups today. |
| **P3** | SQLite job store, full live execute everywhere | Architecture doc Phase 1; unlocks history and faster report queries. |
| **P4** | Real AI lookup provider | Scaffold exists; stub only. |

**Recommendation:** Finish **Phase 0** (this doc’s first section), then implement **Archive diff wizard (Phase 2)** before reference-dir dedupe — it reuses the most existing contracts.

---

## Phase 0 — Scan reliability (in progress)

### Problem observed

- Job stuck visually at **Phase 1a, 37/39 sections, ETA ~6m** for 60+ minutes.
- Process alive on NAS; last progress event ~19:31 UTC on section `_projects`.
- Root cause: long **folder listing / target resolution** with no intermediate events; UI kept last `eta_s`.

### Shipped / shipping in this phase

| Layer | Change |
| --- | --- |
| Engine | `PhaseProgress.pulse()` re-emits progress with `heartbeat: true` without advancing `done` |
| `identify.py` | `os.scandir` + pulse every 30s / 500 entries during listing; pulse every 200 items in resolve loop |
| `engine.py` | Pulse before each category bin in Phase 1a |
| UI | Hide stale ETA when last event `ts` > 2 min; show “last update Xm ago — still working…” |
| UI | Heartbeat events not deduped away (`progressEventKey` includes `ts` for heartbeats) |
| Tests | `test_phase_progress_pulse_emits_heartbeat` |

### Still optional (Phase 0b)

- Process Diagnostics: “stalled?” badge when heartbeats stop > 10 min (distinct from slow listing).
- API `GET /api/jobs/{id}/progress` returns `last_event_ts` for banner polling without WebSocket.

### Operator action for a stuck run

1. **Process Diagnostics → hard-reset** if PID is rogue or you need the UI back.
2. **Wait** if heartbeats show “listing folder…” — huge NAS bins are normal.
3. After reset, re-run dry scan; progress file is `.progress_{job_id}.jsonl` under `dedupe_reports/`.

---

## Phase 1 — Backend feedback & exports (roadmap B)

From `docs/BACKEND_ENHANCEMENT_ROADMAP.md` — not yet complete.

- Vendor add/tester, custom investigation buckets
- Unified export of all feedback JSON
- Dashboard: feedback summary, “apply feedback” dry-run estimate
- Fix duplicate stage-delete path bug (Phase C partial)

**Reports touched:** `Investigation_Breakdown_*.csv`, feedback sidecars, `Duplicate_Review_*.csv`.

**API:** existing `/api/runs/{stamp}/investigation/*`, `/api/runs/{stamp}/duplicates/*`.

---

## Phase 2 — Archive diff wizard (deep design)

### Goal

Double Commander / Beyond Compare style flow **inside Audiotheca**: pick an archive row from a run → see **left: 7-Zip listing**, **right: on-disk extracted folder** → classify extra/missing/keeper → export or execute delete.

This is **not** a re-scan; it composes existing peek + browse APIs.

### Existing contracts (use as-is)

**`Archive_Peek_{stamp}.csv`** (via `load_archive_peek`):

| Column | Wizard use |
| --- | --- |
| `archive_path` | Left pane root; pass to `/api/archive/list?path=` |
| `extracted_folder` | Right pane root; pass to `/api/browse/enriched?path=&stamp=` |
| `verdict` | Pre-filter queue: `REDUNDANT_EXTRACTED`, `PEEK_ONLY`, `MISSING_EXTRACT`, … |
| `name_similarity` | Sort / confidence chip |
| `inferred_product` | Title when folder name is opaque |

**`Archive_Coexistence_{stamp}.csv`** (via `load_coexistence`):

| Column | Wizard use |
| --- | --- |
| `Issue Type` | Wizard step labels (installer sibling, nested archive, etc.) |
| `Archive / Installer` vs `Extracted Folder` | Pair to diff when peek row missing |
| `Suggested Action` | Default button emphasis |

**API already live:**

```
GET  /api/runs/{stamp}/archive-peek?verdict=&query=
GET  /api/runs/{stamp}/coexistence?issue_type=
GET  /api/archive/list?path=&limit=
GET  /api/browse/enriched?path=&stamp=
POST /api/runs/{stamp}/archive-peek/confirm|reject|keeper
POST /api/runs/{stamp}/archive-peek/execute
```

### New API (small)

```
GET /api/runs/{stamp}/archive-diff?archive_path=&folder_path=
```

Response:

```json
{
  "archive_path": "\\\\nas\\…\\foo.rar",
  "folder_path": "\\\\nas\\…\\foo_extracted",
  "archive_entries": [{"name": "…", "size": 123, "is_dir": false}],
  "folder_entries": [{"name": "…", "size": 123, "is_dir": false}],
  "only_in_archive": ["Install.exe"],
  "only_on_disk": ["._MACOSX"],
  "matched": [{"name": "Product.dll", "size_archive": 1, "size_disk": 1}],
  "verdict_hint": "REDUNDANT_EXTRACTED"
}
```

Implementation: server-side join of `/api/archive/list` + `/api/browse` results normalized to basename keys (same as peek matching in engine). No 7-Zip extract required.

Optional:

```
POST /api/runs/{stamp}/archive-diff/export
```

→ writes `Archive_Diff_{stamp}_{id}.csv` for audit (new report name; optional in `download_report` allowlist).

### UI placement

| Location | Behavior |
| --- | --- |
| **Archive tab** | “Open diff wizard” on selected peek row |
| **Explorer dual-pane** | Context menu: “Diff archive vs folder” when one side is `.rar/.7z/.zip` |
| **Wizard steps** | (1) Queue from verdict filter → (2) Side-by-side tree → (3) Confirm keeper → (4) Reuse existing execute |

Reuse components: Explorer tree, archive peek feedback buttons, `ProcessBanner` for execute job.

### Phase 2 deliverables

1. `archive_diff.py` + route + tests (join logic)
2. `ArchiveDiffWizard.tsx` modal or docked panel
3. Wire Archive tab row action + explorer context menu
4. Doc screenshot `archive-diff-wizard.png` + 30s video in `docs/assets/videos/`

---

## Phase 3 — Reference-directory dedupe (dupeGuru-style sketch)

### Goal

Scan library **against a reference tree** (keep reference, flag extras elsewhere). Mode B in dupeGuru terms: “reference directory”.

### Existing contracts to extend

**`Duplicate_Review_{stamp}.csv`** today:

```
Dedup Key, Confidence, Group Kind, …, Full Path, Recommendation, Planned Action
```

**New scan option** (engine + UI Scan panel):

```json
{ "reference_roots": ["D:\\CanonicalLibrary"], "reference_mode": "keep_reference" }
```

**New group kind:** `reference_extra` — member under library root with hash/fingerprint match to reference path.

**Dedup key:** existing fingerprint / hash from `scan_cache.json` + section; add column `Reference Path` when matched.

### Engine sketch

1. Phase 2 scan builds cache as today.
2. **Phase 2b (optional post-pass):** walk `reference_roots`, load hashes from reference cache file `scan_cache_reference.json` or inline walk.
3. For each library item with same content hash as reference item: emit duplicate group with `Recommendation=DELETE` on non-reference path, `KEEP` on reference path.
4. Do **not** merge with in-section duplicate groups unless `group_kind` matches.

### API

```
GET  /api/runs/{stamp}/duplicates?group_kind=reference_extra
POST /api/runs/{stamp}/duplicates/reference-config   # save reference roots for re-run
```

UI: Duplicates tab filter chip **“Reference extras”**; Scan tab subsection “Reference library paths”.

### Why Phase 3 not Phase 2

Requires new engine pass, cache invalidation rules, and UX for “which root is canonical”. Archive wizard delivers value with **zero** new CSV columns.

---

## Phase 4 — SQLite job store & live execute

See `docs/ARCHITECTURE_AND_UI_ROADMAP.md` Phase 1 tables (`jobs`, `items`, `duplicate_groups`, …). Migrates report-first workflow to queryable store; Web UI loads from DB with CSV fallback.

---

## Phase 5 — Media & docs polish

- 7 walkthrough MP4s (`scripts/build_doc_videos.py`)
- Re-capture screenshots without active scan banner on tabs
- Push local commits when GitHub reachable

---

## Suggested commit order

1. `fix: heartbeat progress during NAS listing + stale ETA in UI` (Phase 0)
2. `docs: phased roadmap with archive diff wizard design`
3. `feat: archive diff API + wizard MVP` (Phase 2)
4. `feat: reference-root dedupe pass` (Phase 3)

---

## Related docs

- [Architecture & UI Roadmap](ARCHITECTURE_AND_UI_ROADMAP.md)
- [Backend Enhancement Roadmap](BACKEND_ENHANCEMENT_ROADMAP.md)
- [Feature Guide](FEATURE_GUIDE.md)
- [Debug Runbook — Duplicate & Archive sections](DEBUG_RUNBOOK.md)
