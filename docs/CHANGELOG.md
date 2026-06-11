# Changelog

## 9.7.1

- Staged live pre-flight summary before Phase 3 restructure moves.
- Scene rename plan always written; apply gated by `SCENE_AUTO_RENAME`.
- Scene renames always item-by-item on live runs; skip weak names and `MISSING_PART01`.
- Listing-artifact fix for 7-Zip timestamps in inferred product names (`strip_listing_artifact`).
- `gen_archive_delete_candidates.py` for redundant `MATCHES_EXTRACTED_FOLDER` archives.

## 9.7.0

- **Archive peek integrated** — Phases 1.6–1.8 list `.zip`/`.rar`/`.7z` contents via 7-Zip without extracting; writes `Archive_Peek_*.csv`.
- **Scene-hash intelligence** — Peeks multipart archives inside numeric release folders; `Scene_Archive_Peek_*.csv` + `Multipart_Archive_Diagnostic_*.csv` (missing part01, gaps, corrupt part01 — e.g. `287901`).
- **Scene auto-rename** — Infers product title from archive listing; `Scene_Rename_Plan_*.csv`; live rename when `SCENE_AUTO_RENAME = True` (respects `DRY_RUN`).
- **Progress ETA** — Each phase prints `elapsed` + `ETA` per category/section/group; scan uses tqdm bar with remaining time.
- **Modules** — `archive_peek.py`, `progress.py`; standalone `peek_archives.py` CLI for re-peeking old CSVs.

## 9.6.1

- `largest_files` stores relative paths for correct nested content-hash checks.
- `move_and_merge` returns `False` on collisions; child failures propagate.
- `vendor_db.py` duplicate dict keys removed (Celemony, Voxengo, Melodyne, Kush).
- Scan worker failures → `Scan_Failures_*.csv`.
- `tests/test_pure.py` — unit tests for core helpers.

## 9.6.0

- Initial documented release: scan cache, investigation buckets, coexistence detection, strict dedupe.
