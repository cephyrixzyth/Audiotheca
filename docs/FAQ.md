# Audiotheca — FAQ

Engine version: **10.0.0** · Web UI: **1.0.12**

See the [main README](../README.md) for quick start and [User Guide](USER_GUIDE.md) for tab workflows.

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

Rough guide for ~7,200 items on a network share: **45–120+ minutes** depending on latency, cache hits, worker count, and archive peek (7-Zip listing adds time on scene-hash folders). Second runs are faster when `scan_cache.json` is warm. Phases print **ETA** in the terminal.

### Do I need 7-Zip?

**Yes**, for archive peek on `.rar`/`.7z`/`.iso`. Without it, scene-hash identity and sibling archive listing will show `NEEDS_7ZIP`. `.zip` peek works without 7-Zip.

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

Numeric/hash folders (e.g. `287901`, `7935P`) common in `=` bins. As of **9.7.0**:

1. Check **`Scene_Archive_Peek_*.csv`** for `inferred_product` from archive listing.
2. Check **`Multipart_Archive_Diagnostic_*.csv`** — `MISSING_PART01` means an incomplete download (only part110+ on disk).
3. Enable **`SCENE_AUTO_RENAME`** for automatic rename when identity is confident (live run, ≥ `SCENE_RENAME_MIN_SIZE_MB`).

Example: `7935P` peeks as *Sonus Paradisi Segovia Cathedral Hauptwerk*; `287901` often shows `MISSING_PART01` (part01 absent).

### What is `Archive_Peek_*.csv`?

Lists files **inside** archives next to extracted folders without extracting them. Verdict `MATCHES_EXTRACTED_FOLDER` means you can delete the archive after verifying the folder. Re-run peek alone: `python peek_archives.py`.

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

New in 9.7: `Archive_Peek_*.csv`, `Scene_Archive_Peek_*.csv`, `Multipart_Archive_Diagnostic_*.csv`, `Scene_Rename_Plan_*.csv` — see [Feature Guide](FEATURE_GUIDE.md).

---

## Configuration

### Do I need to delete the cache after changing vendor_db.py?

Not strictly — cache stores scan sizes/OS flags, not vendor routes. Bump `CACHE_SCHEMA` when scan tree format changes; identification-only `ENGINE_VERSION` bumps keep the warm cache.

### Can I scan only one section?

Use **Scan tab → target paths** or API `target_paths` for focused rescans. For a full CLI run of one bin:

```powershell
python main.py --dry-run --root "D:\YourLibrary\_software\_audio\sectionA"
```

Or temporarily set `AUDIOTHECA_LIBRARY_ROOT` to that bin path.

### What if the share is read-only?

Dry runs work. Live runs fail at startup with "Drive is read-only."

---

## Future / not supported

### Can it dedupe by audio content (WAV/FLAC)?

### Does Audiotheca use AcoustID / Chromaprint?

**Chromaprint / `fpcalc` support ships** for local acoustic fingerprinting (Environment panel / `audio_fingerprint.py`). **AcoustID / MusicBrainz online lookup** is available via `POST /api/audio/acoustid-lookup` when outbound is allowed and `ACOUSTID_CLIENT_KEY` is set (skipped in air-gap). RF64/MBWF containers are detected for BWF metadata and WAV info.

### Can it rename files to UCS standard?

Not yet. UCS taxonomy integration is on the roadmap for sample libraries.

### Does it integrate with Soundminer?

No direct integration. Sidecar JSON metadata is compatible with manual Soundminer workflows.

---

## Web UI

### How do I open the dashboard?

```powershell
cd "C:\path\to\audiotheca"
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
.\start-ui.ps1
```

Open **http://localhost:5173**. API health: http://127.0.0.1:8787/api/health.

First time on a new machine: follow **[Testing Guide](TESTING.md)**.

### Why does the UI scan the wrong drive?

Set `AUDIOTHECA_LIBRARY_ROOT` before starting the API. The UI reads allowed roots from `/api/security/library-roots` when the API is running.

### What are underscore vendor folders?

Some libraries use `_8Dio`, `_Kontakt Libraries`, etc. The engine skips `_`-prefixed folders unless whitelisted. Use the **Space recovery** tab → seed/whitelist → full dry scan. Config: `dedupe_reports/feedback/underscore_whitelist.json`.

### What is Space recovery?

UI + `space_recovery.py` for coexistence issues (deep installers, archive+extract siblings) and optional hardlink/bloat reports. Does not delete files automatically — generates CSV + PowerShell preview scripts.

### Windows upgrade fails with “error opening file for writing”

The installer cannot overwrite **Audiotheca.exe** or the bundled **api-server** / **audiotheca-engine** sidecars while they are running.

1. Fully quit Audiotheca (taskbar → Exit).
2. Task Manager → end `Audiotheca`, `api-server`, and `audiotheca-engine`.
3. Or: `powershell -ExecutionPolicy Bypass -File scripts\kill-audiotheca.ps1`
4. Re-run the installer **as Administrator**.

See [Install guide — Upgrading on Windows](INSTALL.md#upgrading-on-windows-fix-error-opening-file-for-writing).

### `npm: not recognized`

Node.js is not installed or not on PATH. Install from [nodejs.org](https://nodejs.org/) or run `winget install OpenJS.NodeJS.LTS`, then **close and reopen** the terminal. Use `.\start-api.ps1` if you only need the API.

### Can I use the UI without Node.js?

Not for the React dev UI. Use `.\start-api.ps1` and hit JSON endpoints directly, or review CSV reports in `dedupe_reports/`. The Tauri release build bundles the UI without requiring Node for end users.

### Where do duplicate keeper choices save?

`dedupe_reports/decisions/approved_{stamp}.json` — export from the Duplicates tab.

### What is the in-app file explorer?

Engine **10.0+** adds **Browse** on path links and API routes `/api/browse` and `/api/archive/list`. You can list folders and archive contents inside the UI without opening Windows Explorer or extracting archives.

### What is AI lookup?

When heuristics cannot identify a product, Phase **1b-fallback** can queue contextual lookup using release metadata (NFO/readme). Results appear in the **Scan tab → AI analyzer** and cache under `dedupe_reports/ai_lookup_cache/`. Skip the phase in processing flow if you want a faster dry-run.

### Where are UI themes configured?

Use the ◐ theme switcher in the top bar, or **Environment → Themes** to duplicate built-in presets, edit colors, and import/export JSON themes (stored in browser localStorage).

### Where is Help in the UI?

The **Help** tab is the **last** tab in the top bar (after Vendors). It mirrors quick install/workflow notes; full docs live in [docs/README.md](README.md) and the [main README](../README.md).

---

## macOS desktop

### I installed from the DMG on my M-series Mac and nothing happens

This usually means **Gatekeeper** blocked the unsigned download, or the wrong architecture DMG was used.

1. Use the **Apple Silicon** build (`*_aarch64.dmg` / `*_arm64.dmg`), not the Intel `*_x64.dmg`.
2. Drag the app to **Applications**, then **right-click → Open** (not double-click) on first launch.
3. If still no window:
   ```bash
   xattr -dr com.apple.quarantine /Applications/Audiotheca.app
   codesign --force --deep --sign - /Applications/Audiotheca.app
   ```
   Or run `./scripts/macos_fixup_app.sh` from a repo checkout.
4. Check the startup log:  
   `~/Library/Application Support/com.audiotheca.desktop/audiotheca-desktop.log`
5. Open **Console.app** and filter for `Audiotheca` if the app crashes immediately.

From **1.0.12** onward, the desktop shell stores data in Application Support (writable) instead of inside the `.app` bundle, and ad-hoc signing is applied at build time.

---

## Getting help

1. [Main README](../README.md)
2. [Quick User Guide](USER_GUIDE.md)
3. [Debug Runbook](DEBUG_RUNBOOK.md)
4. Latest `Run_Summary_*.txt` and `dedupe_engine.log`
5. Note `ENGINE_VERSION` printed at run start when reporting issues
