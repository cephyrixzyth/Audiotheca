# Backend Enhancement Roadmap — Per-Module Feedback & Corrections

Engine **10.0.0** · UI **1.0.3**

**Status (2026-07-06):** Phases A–D and unified feedback exports are **shipped**. See [PHASED_ROADMAP.md](PHASED_ROADMAP.md) and [SPEC_CATALOG.md](SPEC_CATALOG.md).

This document defines **what to build in each UI module** so your manual review produces structured output the engine can consume on the next run — not just CSV reports to read.

**Pattern already working:** Duplicates tab → `dedupe_reports/feedback/duplicate_feedback.json` → `engine_hints.json` → engine skips bad groups.

**Goal:** Repeat that pattern for Investigation, Restructure, Archives, Scene renames, and Vendor DB — one unified export you can review and feed back.

---

## Unified feedback architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  UI modules (per-tab corrections)                                │
│  Investigation │ Restructure │ Duplicates │ Archives │ Scene   │
└────────────────────────────┬────────────────────────────────────┘
                             │ POST corrections
┌────────────────────────────▼────────────────────────────────────┐
│  dedupe_reports/feedback/                                        │
│    investigation_feedback.json   (global, cumulative)            │
│    restructure_feedback.json                                     │
│    duplicate_feedback.json       ✓ exists                        │
│    archive_feedback.json                                         │
│    scene_feedback.json                                           │
│    vendor_overrides.json         (keywords you add in UI)        │
│    bucket_overrides.json         (custom buckets you define)     │
└────────────────────────────┬────────────────────────────────────┘
                             │ export
┌────────────────────────────▼────────────────────────────────────┐
│  Backend_Enhancement_Export_{stamp}.csv  (human review)          │
│  engine_hints.json                       (machine read, merged)    │
└────────────────────────────┬────────────────────────────────────┘
                             │ next scan
┌────────────────────────────▼────────────────────────────────────┐
│  main.py — apply overrides before classify / dedupe / route      │
└─────────────────────────────────────────────────────────────────┘
```

### Export columns (all modules)

| Column | Purpose |
|--------|---------|
| `Module` | INVESTIGATION, RESTRUCTURE, DUPLICATE, ARCHIVE, SCENE, VENDOR |
| `Action` | CORRECT, REJECT, OVERRIDE, ADD, MERGE, LINK |
| `Run Stamp` | Which dry run the finding came from |
| `Path / Key` | Item path, dedup key, or scene id |
| `Field` | vendor, bucket, destination, keeper, verdict, … |
| `Old Value` | What the engine produced |
| `New Value` | Your correction |
| `Reason` | Dropdown + free-text note |
| `Created` | ISO timestamp |

---

## Module 1 — Investigation (highest priority)

**Current state:** Read-only inbox. ~2,800 items in typical run across 8 fixed buckets. No way to fix mis-buckets or teach vendor ID from the UI.

**Why it matters:** Investigation is the largest manual workload. Every correction you make here should shrink the next run's `_requiresinvestigation` count.

### Existing buckets (`main.py`)

| Bucket | Typical fix |
|--------|-------------|
| `_unknown_vendor` | Add vendor keywords; or force vendor on this path |
| `_scene_release_id` | Wait for archive peek / scene rename; or manual vendor |
| `_library_internal` | Link to parent product folder |
| `_likely_component` | Merge into parent; mark as non-target |
| `_vendor_conflict` | Pick winning vendor; add blocklist pair |
| `_unverified_vendor` | Add vendor to `vendor_db.py` |
| `_generic_name` | Add strong keyword; or rename folder |
| `_preset_or_snippet` | Link to parent library; or new bucket |

### Features to build

| Feature | UI control | Backend effect |
|---------|------------|----------------|
| **Reassign bucket** | Dropdown on row | Override `classify_investigation()` for this path |
| **Set vendor** | Vendor picker + keywords | Writes `vendor_overrides.json`; engine uses before ID tiers |
| **Add vendor to DB** | Form: company name + keywords + category | Appends to `vendor_db.py` or `vendor_overrides.json` |
| **Link to parent** | Pick existing product path | `_likely_component` → route under parent; skip as standalone target |
| **Mark resolved** | "Not investigation" | Path blocklist — never route to `_requiresinvestigation` again |
| **Create custom bucket** | Name + description + rule hint | `bucket_overrides.json`; optional new folder under investigation |
| **Bulk by fingerprint** | Select all with same fingerprint | One correction applies to N items |
| **Scene hash helper** | Show archive peek result inline | Jump to Scene tab with context |

### Investigation correction reasons (dropdown)

- `wrong_bucket` — item belongs in a different bucket
- `vendor_known` — I know the vendor (add keywords)
- `is_component` — subfolder of another product
- `not_a_product` — junk / OS / promo (route to bloat)
- `scene_needs_peek` — defer until archive listed
- `false_positive` — should be READY, not investigation

### Engine consumption (next scan)

```python
# Pseudocode — investigation_hints.json
{
  "path_vendor_overrides": {"Z:\\...\\Noire Library": "Native Instruments"},
  "path_bucket_overrides": {"Z:\\...\\Documentation": "_library_internal"},
  "resolved_paths": ["Z:\\...\\fixed-item"],  # skip investigation
  "parent_links": {"Z:\\...\\Samples": "Z:\\...\\Kontakt Library"},
  "custom_buckets": {"_my_manual_review": "Items I flagged for manual sorting"}
}
```

---

## Module 2 — Vendor database (cross-cutting)

**Current state:** `vendor_db.py` — ~700 vendors, edit by hand. No UI.

### Features to build

| Feature | UI | Export |
|---------|-----|--------|
| **Add vendor** | Company, category, keywords[] | `vendor_overrides.json` + optional `vendor_db_patch.json` |
| **Add keyword to existing** | Search vendor → add keyword | Merged at scan time |
| **Alias map** | "NI" → "Native Instruments" | PE/name normalization |
| **Blocklist keyword** | Prevent false vendor match | `keyword_blocklist` |
| **Test match** | Type folder name → see which tier hits | Debug without full scan |

### Export for backend

`Vendor_DB_Patch_{stamp}.json` — you review, then merge into `vendor_db.py` or auto-apply if overrides file exists.

---

## Module 3 — Custom buckets

**Current state:** Buckets hardcoded in `INVESTIGATION_BUCKETS` in `main.py`.

### Features to build

| Feature | Description |
|---------|-------------|
| **Define bucket** | `_awaiting_scene_peek`, `_manual_vendor_entry`, … |
| **Assign items** | Drag or bulk-assign from investigation inbox |
| **Bucket rules (later)** | Optional: "paths matching regex → bucket" |

Stored in `bucket_overrides.json`:

```json
{
  "custom_buckets": {
    "_awaiting_license": "License files pending manual check"
  },
  "path_assignments": {
    "Z:\\...\\item": "_awaiting_license"
  }
}
```

Engine: `classify_investigation()` checks `path_assignments` first, then custom bucket list, then default logic.

---

## Module 4 — Restructure

**Current state:** Read-only plan preview. Live moves happen in CLI with section approval.

### Features to build

| Feature | UI control | Backend effect |
|---------|------------|----------------|
| **Override destination** | Edit planned path per row | `restructure_overrides.json` |
| **Reject route** | "Should stay in place" | Path blocklist for moves |
| **Force section** | Move to `a/` vs `s/` | Section override |
| **Approve section** | Bulk approve from UI | Replace CLI section prompts (Stage 1+) |
| **Mark READY false positive** | Item flagged NEEDS REVIEW wrongly | Investigation feedback link |

### Export

`Restructure_Corrections_{stamp}.csv` — path, current dest, corrected dest, reason.

---

## Module 5 — Duplicates (partially built ✓)

**Current state:** Keeper pick, bad match, stage deletes, manual dupe report, feedback CSV.

### Still to build

| Feature | Priority |
|---------|----------|
| Fix library root inference (`Z:\_software\_audio` not `Z:\`) | **P0 bug** |
| Show execute results per path in UI | P1 |
| Wire `approved.json` into engine live execute | P1 |
| Bulk keeper = engine recommendation | P2 |
| Fingerprint blocklist from rejections | P2 |

---

## Module 6 — Archives

**Current state:** Peek verdicts, delete-candidate stats. Offline PowerShell for redundant archives.

### Features to build

| Feature | UI control | Backend effect |
|---------|------------|----------------|
| **Reject verdict** | "Archive is NOT redundant" | Skip `MATCHES_EXTRACTED_FOLDER` next time |
| **Confirm delete** | Per-row confirm | Feed delete script |
| **Keep archive not folder** | Invert keeper | Archive feedback |
| **Multipart note** | Flag incomplete set | Diagnostic override |

---

## Module 7 — Scene renames

**Current state:** Plan preview only. Live rename gated by `SCENE_AUTO_RENAME`.

### Features to build

| Feature | UI control | Backend effect |
|---------|------------|----------------|
| **Edit proposed name** | Inline edit | Override rename plan |
| **Reject rename** | Bad inference | Blocklist scene id |
| **Approve rename** | Per-row or bulk | Queue for Stage 2 live |
| **Missing part01 flag** | Mark incomplete | Skip auto-rename |

---

## Module 8 — Scan / Dashboard

### Features to build

| Feature | Description |
|---------|-------------|
| **Feedback summary card** | Count corrections per module since last scan |
| **"Apply feedback" dry run** | Estimate delta: −N investigation, −M dupes |
| **Export all feedback** | One button → `Backend_Enhancement_Export_{stamp}.csv` |
| **Import feedback** | Load JSON from another machine |

---

## Recommended implementation phases

### Phase A — Investigation MVP ✓ shipped

1. ~~`investigation_feedback.py`~~ ✓
2. ~~API: `POST /runs/{stamp}/investigation/correct`~~ ✓
3. ~~UI: InvestigationInbox row actions~~ ✓
4. ~~Export: `Investigation_Feedback_Export_{stamp}.csv`~~ ✓
5. ~~Engine: `investigation_hints.json` in classify / route~~ ✓

### Phase B — Vendor & buckets (1 week)

1. Vendor add form + keyword tester
2. Custom bucket creator
3. `vendor_overrides.json` + `bucket_overrides.json`
4. Merge export into single `Backend_Enhancement_Export`

### Phase C — Restructure + execute from UI (1–2 weeks)

1. Destination overrides
2. Section approve from UI
3. Fix duplicate stage-delete root path bug

### Phase D — Archives + Scene polish (1 week)

1. Verdict reject / confirm
2. Scene rename approve queue

---

## Investigation inbox — proposed UI wireframe

```
┌──────────────────────────────────────────────────────────────────┐
│ Bucket [all ▼]  Search [________]  [Export feedback]  [Add vendor]│
├──────────────────────────────────────────────────────────────────┤
│ a │ Noire Library          │ _unknown_vendor │ [Set vendor ▼]    │
│   │ Z:\...\Noire Library   │                 │ [Reassign ▼]      │
│   │                          │                 │ [Link parent…]    │
│   │                          │                 │ [✓ Resolved]      │
├──────────────────────────────────────────────────────────────────┤
│ = │ 287901                 │ _scene_release_id│ [Peek result]    │
│   │                          │ MISSING_PART01  │ [Defer rename]   │
└──────────────────────────────────────────────────────────────────┘
```

---

## What you can do today (no new code)

| Task | How |
|------|-----|
| Add vendors | Edit `vendor_db.py` → dry run |
| Change buckets | Edit `INVESTIGATION_BUCKETS` in `main.py` |
| Duplicate corrections | Duplicates tab → Export feedback CSV |
| Archive cleanup | `gen_archive_delete_candidates.py` → PowerShell |
| Review investigation | Investigation tab → filter by bucket → manual notes in spreadsheet |

---

## Success metrics (per re-run)

Track in Dashboard after feedback applied:

| Metric | Target |
|--------|--------|
| Investigation count | Down 10–30% per feedback cycle |
| `_unknown_vendor` bucket | Largest drop |
| `_unverified_vendor` | Drops after vendor DB patches |
| False duplicate groups | Zero re-appearance after reject |
| READY % | Up (52% → 60%+ over iterations) |

---

## Related docs

- [Feature Guide](FEATURE_GUIDE.md) — engine phases and buckets
- [User Guide](USER_GUIDE.md) — how to run UI and staged rollout
- [Architecture & UI Roadmap](ARCHITECTURE_AND_UI_ROADMAP.md) — long-term product plan
