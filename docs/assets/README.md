# Documentation media assets

This folder holds **screenshots and walkthrough videos** referenced from the [main README](../../README.md) and other guides.

> **Tip:** Use a consistent library root label in screenshots (for example `D:\Libraries\_audio`) and blur or crop anything you do not want in public docs.

## Folder layout

```
docs/assets/
├── README.md          ← this file
├── ASSETS.md          ← checklist of every required file
├── screenshots/       ← PNG or WebP stills
├── videos/            ← MP4 walkthroughs (source)
└── gifs/              ← optimized GIFs for GitHub README + Help tab
```

## Quick capture

```powershell
# Seed demo library + reports (no servers)
python scripts/seed_demo_library.py

# Stills only (API + UI must be running on capture ports)
$env:AUDIOTHECA_CAPTURE_UI_PORT="5175"
$env:AUDIOTHECA_CAPTURE_API_PORT="8788"
python scripts/capture_screenshots_only.py

# GIFs + copy to ui/public/help/
python scripts/build_doc_gifs.py
```

Full automated pipeline (starts servers, records videos): `python scripts/capture_doc_assets.py`

## Screenshots to capture

Capture at **1920×1080** or your usual monitor size. Save as PNG (lossless UI text) or WebP (smaller repo size).

### Core (in README today)

| File | What to show | When to capture |
|------|----------------|-----------------|
| `screenshots/ui-overview.png` | Grouped top nav, sidebar, Dashboard with a loaded run | After a completed dry-run |
| `screenshots/dashboard-gauges.png` | Route-ready / identification gauges and run compare | Same run as above |
| `screenshots/scan-panel.png` | Scan tab: processing flow editor, phase toggles, AI lookup | During or right after a dry-run |
| `screenshots/investigation-inbox.png` | Investigation tab with bucket filter and corrected rows | After triage session |
| `screenshots/duplicates-review.png` | Duplicate group with keeper selected | When duplicate CSV has groups |
| `screenshots/restructure-preview.png` | Restructure routes with destination preview | Dry-run with restructure plan |
| `screenshots/scene-renames.png` | Scene renames tab with hash → product proposals | Demo run with scene plan |
| `screenshots/scan-audit.png` | Scan audit table with ID methods | Same demo run |
| `screenshots/skipped-files.png` | Skipped tab — failures, gaps, cache hits | Same demo run |
| `screenshots/file-explorer.png` | **Library** button — tree, optional audio preview on WAV | Click Library from top bar |
| `screenshots/archives-verdicts.png` | Archives tab with peek verdicts | After archive peek phase |
| `screenshots/archive-diff-wizard.png` | Diff modal — archive vs extracted folder | Archives → Diff on a pair |
| `screenshots/security-malware.png` | Security tab: scan controls and findings | Optional demo folder |
| `screenshots/environment-themes.png` | Environment → theme studio | Any theme selected |
| `screenshots/help-panel.png` | Help tab (last primary tab) with a topic open | Default install |

### 1.0.5 additions (shipped)

| File | What to show |
|------|----------------|
| `screenshots/investigation-lookup.png` | Investigation → **Investigation lookup** (WEB-SPDR / TAG-GEN / NFO-PARSE) |
| `screenshots/environment-spec-catalog.png` | Environment → **Architecture spec catalog** (94 codes, done counts) |
| `screenshots/environment-orchestration.png` | Environment → **Orchestration tools** panel |
| `screenshots/environment-cloud-storage.png` | Environment → **Cloud & storage telemetry** |
| `screenshots/audio-preview.png` | Library → select demo `.wav`; waveform + LUFS/BPM/key badges |
| `screenshots/dropzone-overlay.png` | Library → drag files to show DropZone overlay |

## Videos to record

Record at **1080p**, 30 fps, with brief on-screen captions if helpful. Keep each video focused on one workflow (3–8 minutes).

| File | Topic | Suggested script |
|------|--------|------------------|
| `videos/first-scan-walkthrough.mp4` | Install → set library root → first dry-run → read Dashboard | Match [Testing guide](../TESTING.md) |
| `videos/scan-phases-and-flow.mp4` | Processing flow presets, skipping phases, reading WebSocket log | Scan tab deep dive |
| `videos/investigation-and-vendors.mp4` | Investigation corrections → Vendors keywords → rescan | Triage unknown items |
| `videos/restructure-live-staging.mp4` | Preview routes → section approval → **confirm live** guardrails | Stage 1 rollout only |
| `videos/file-explorer-and-archives.mp4` | Library explorer, archive list without extract, redundant verdicts | Explorer + Archives |
| `videos/archive-diff-wizard.mp4` | Diff wizard — archive vs extracted sibling | Archives tab |
| `videos/ai-lookup-review.mp4` | Scan tab AI analyzer, confirm/reject lookup, cache | After unknown targets queue |
| `videos/security-and-space-recovery.mp4` | Malware heuristics, underscore whitelist, coexistence summary | System tabs |

Optional 1.0.5 topics (see [ASSETS.md](ASSETS.md)): Environment orchestration/spec catalog (`environment-and-spec-catalog.mp4`), investigation lookup (`investigation-lookup.mp4`), audio preview + DropZone (`audio-preview-library.mp4`).

## GIFs for GitHub README

GitHub renders GIFs inline but not MP4. After recording or rebuilding MP4s, run:

```powershell
python scripts/build_doc_gifs.py
```

This writes optimized GIFs to `gifs/` (~1280px wide, 10 fps) and copies screenshots + GIFs to `ui/public/help/` for the in-app Help tab.

## Adding files to the repo

1. Place stills under `screenshots/` and MP4s under `videos/` using the exact names in [ASSETS.md](ASSETS.md).
2. Run `python scripts/build_doc_gifs.py` to regenerate GIFs and sync Help tab assets.
3. Re-open [README.md](../../README.md) — embed new images and add captions.

## Related documentation

- [User Guide](../USER_GUIDE.md) — day-to-day workflows
- [Feature Guide](../FEATURE_GUIDE.md) — scan phases and reports
- [Spec catalog](../SPEC_CATALOG.md) — 94-code registry
- [Testing Guide](../TESTING.md) — smoke-test checklist for captures
