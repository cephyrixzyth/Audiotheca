# Audiotheca — FAQ

## General

### What is Audiotheca?

Audiotheca is an audio library deduplication and routing engine. It scans VST plugins, sample libraries, installers, and scene releases on local or network storage, then produces reports and (optionally) reorganizes files into vendor folders.

### Why the name Audiotheca?

From *audio* + *theca* (a case or storage container). It reflects the project's purpose: cataloguing and shelving a large software library.

Suggested repo name: **`audiotheca`**

### Will it delete my files?

No permanent deletion. Suspected duplicates are **moved to `_delete-canidates`** at the root of your audio folder. You review and delete manually.

With `DRY_RUN = True` (default), **nothing moves at all** — only reports are generated.

### Does it work on network drives?

Yes — it was built for high-latency SMB/CIFS shares. Use conservative `MAX_WORKERS` (4–8) and depth limits. Expect long scan times on libraries with thousands of items.

---

## Before running

### Should I always dry-run first?

**Yes.** Every configuration change, vendor_db update, or engine upgrade should get a dry run. Compare `Run_Summary_*.txt` counts between runs.

### How long does a scan take?

Rough guide for ~7,700 items on a network share: **30–90+ minutes** depending on latency, cache hits, and worker count. Second runs are faster when `scan_cache.json` is warm.

### Why is there no terminal output for a long time?

Python buffers stdout when not attached to an interactive terminal. Use:

```powershell
$env:PYTHONUNBUFFERED=1
python main.py
```

Progress also logs to `dedupe_engine.log` next to `main.py`.

---

## Identification & routing

### Why did an item go to `_requiresinvestigation`?

Check **`Investigation_Breakdown_*.csv`**. Common reasons:

- No vendor keyword matched (`_unknown_vendor`)
- Scene hash folder with no product name (`_scene_release_id`)
- Documentation/Samples subfolder treated as standalone (`_library_internal`)
- Same fingerprint as another product (`_likely_component`)
- NFO scraped a name not in `vendor_db.py` (`_unverified_vendor`)

### Why didn't it recognize a vendor I know is there?

1. Vendor missing from `vendor_db.py` — add keywords
2. Folder name doesn't contain any keyword (scene hash release)
3. Only PE header has company name but `pefile` isn't installed
4. Item is a **component** of a library (Documentation, Update) not the product root

### Why did two similar folders not group as duplicates?

Strict matching requires **same vendor + same fingerprint + high name similarity**. Common exclusions:

- Different vendors (even if product names match)
- Generic fingerprint (`documentation`, `presets`)
- LOW confidence (filtered out)
- Content check showed files differ (downgraded to MEDIUM)

### What's the difference between VERSION_UPGRADE and SAME_VERSION duplicates?

- **SAME_VERSION** — same product version; likely a true duplicate (nested wrapper, copy in two sections)
- **VERSION_UPGRADE** — same product, different version; engine recommends keeping the **newest** by version key

---

## Duplicates

### What does HIGH vs MEDIUM confidence mean?

| Level | Typical meaning | Live action |
| --- | --- | --- |
| HIGH | Same version, high name match, similar size | Prompted for staging (or auto if content MATCH) |
| MEDIUM | Version upgrade, size mismatch, or content differs | Report only — manual review |
| LOW | Weak match | Not shown in duplicate review |

### Why were there 915 duplicate groups in an old run but only 82 in a newer one?

Early versions used over-aggressive fingerprinting (ignored vendor/version). v9.2+ requires vendor + fingerprint + similarity, which eliminated most false positives like unrelated `Documentation` folders grouping together.

### Should I auto-delete HIGH confidence duplicates?

**Not recommended for first live run.** Use `ACTION_MODE = "item"` and review each staging decision. Even HIGH + MATCH can be wrong for sample libraries where two folders have similar names but different content.

---

## Investigation buckets

### Can I rename or remove investigation subfolders?

Yes — they're just organizational targets. If you change bucket names in `INVESTIGATION_BUCKETS` in `main.py`, update any manual workflows accordingly.

### What should I do with `_likely_component` items?

These share a fingerprint with a confirmed product elsewhere. Usually they are Documentation, Update, or Preset subfolders that were scanned as standalone targets. Merge them into the parent product folder manually or adjust target discovery so the whole library is one item.

### What about `_scene_release_id` folders?

These are release-group hash folders (common in `=` bins). Open the folder, identify the actual product inside, and either rename the wrapper or add vendor keywords for the inner product name.

---

## Live runs

### What do the approval modes mean?

| Mode | Best for |
| --- | --- |
| `section` | Bulk approve all moves in `a/`, then `b/`, etc. |
| `item` | Maximum control — confirm every single action |
| `auto` | Trusted re-run after dry-run review; still stages only safe HIGH dupes |

### I approved a section by mistake. Can I undo?

Audiotheca does not maintain an undo log. Restore from backup or move items back using `_audit_info.json` sidecars (original path is recorded). This is why dry runs and item mode exist.

### What folders does Audiotheca create on the library root?

| Folder | Purpose |
| --- | --- |
| `_requiresinvestigation/` | Unidentified items (with sub-buckets) |
| `_delete-canidates/` | Staged duplicate copies |
| `_non_pc_quarantine/` | Mac/Linux-only content |
| `_tonex libraries/` | TONEX/AmpliTube captures |
| `_dedupe_reports/` | Report copies (when share writable) |

---

## Configuration

### Do I need to delete the cache after changing vendor_db.py?

Not strictly — cache stores scan sizes/OS flags, not vendor routes. But after logic changes, bump `ENGINE_VERSION` which auto-invalidates cache entries from older versions.

### Can I scan only one section?

Not built-in. Workaround: temporarily set `ROOT_DIR` to a single bin path (e.g. `Z:\_software\_audio\a`) for a focused run.

### What if the share is read-only?

Dry runs work. Live runs fail at startup with "Drive is read-only."

---

## Future / not supported

### Can it dedupe by audio content (WAV/FLAC)?

Not currently. It uses metadata fingerprinting and sparse file hashing. Audio fingerprinting (AcoustID/Chromaprint) is a possible future addition.

### Can it rename files to UCS standard?

Not yet. UCS taxonomy integration is on the roadmap for sample libraries.

### Does it integrate with Soundminer?

No direct integration. Sidecar JSON metadata is compatible with manual Soundminer workflows.

---

## Getting help

1. Check [Debug Runbook](DEBUG_RUNBOOK.md)
2. Review latest `Run_Summary_*.txt` and `dedupe_engine.log`
3. Note `ENGINE_VERSION` printed at run start — include it when reporting issues
