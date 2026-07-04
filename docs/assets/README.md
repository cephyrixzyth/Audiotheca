# Documentation media assets

This folder holds **screenshots and walkthrough videos** referenced from the [main README](../../README.md) and other guides. The paths below are placeholders until you capture real media from a running Audiotheca instance.

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

## Screenshots to capture

Capture at **1920×1080** or your usual monitor size. Save as PNG (lossless UI text) or WebP (smaller repo size).

| File | What to show | When to capture |
|------|----------------|-----------------|
| `screenshots/ui-overview.png` | Full browser window: top tabs, sidebar, Dashboard with a loaded run | After a completed dry-run |
| `screenshots/dashboard-gauges.png` | Route-ready / identification gauges and run compare | Same run as above |
| `screenshots/scan-panel.png` | Scan tab: processing flow editor, phase toggles, live progress | During or right after a dry-run |
| `screenshots/investigation-inbox.png` | Investigation tab with bucket filter and a few corrected rows | After triage session |
| `screenshots/duplicates-review.png` | Duplicate group with keeper selected | When duplicate CSV has groups |
| `screenshots/restructure-preview.png` | Restructure routes with destination preview | Dry-run with restructure plan |
| `screenshots/file-explorer.png` | In-app **Browse** panel listing a folder or archive contents | Click **Browse** on any PathLink |
| `screenshots/archives-verdicts.png` | Archives tab with peek verdicts | After archive peek phase |
| `screenshots/security-malware.png` | Security tab: heuristic scan or hash lookup | Optional demo folder |
| `screenshots/environment-themes.png` | Environment tab → Themes section with swatches | Any theme selected |
| `screenshots/help-panel.png` | Help tab (last tab) with a topic open | Default install |

## Videos to record

Record at **1080p**, 30 fps, with brief on-screen captions if helpful. Keep each video focused on one workflow (3–8 minutes).

| File | Topic | Suggested script |
|------|--------|------------------|
| `videos/first-scan-walkthrough.mp4` | Install → set library root → first dry-run → read Dashboard | Match [Testing guide](../TESTING.md) |
| `videos/scan-phases-and-flow.mp4` | Processing flow presets, skipping phases, reading WebSocket log | Scan tab deep dive |
| `videos/investigation-and-vendors.mp4` | Investigation corrections → Vendors keywords → rescan | Triage unknown items |
| `videos/restructure-live-staging.mp4` | Preview routes → section approval → **confirm live** guardrails | Stage 1 rollout only |
| `videos/file-explorer-and-archives.mp4` | Browse panel, archive list without extract, redundant archive verdicts | 10.0.0 explorer features |
| `videos/ai-lookup-review.mp4` | Scan tab AI analyzer, confirm/reject lookup, cache | After unknown targets queue |
| `videos/security-and-space-recovery.mp4` | Malware heuristics, underscore whitelist, coexistence summary | Optional advanced day |

## GIFs for GitHub README

GitHub renders GIFs inline but not MP4. After recording or rebuilding MP4s, run:

```powershell
python scripts/build_doc_gifs.py
```

This writes optimized GIFs to `gifs/` (~1280px wide, 10 fps) and copies screenshots + GIFs to `ui/public/help/` for the in-app Help tab.

| File | Topic |
|------|--------|
| `gifs/first-scan-walkthrough.gif` | Install → first dry-run → Dashboard |
| `gifs/scan-phases-and-flow.gif` | Processing flow presets, skipping phases |
| `gifs/investigation-and-vendors.gif` | Investigation corrections → Vendors |
| `gifs/restructure-live-staging.gif` | Preview routes → staged live execute |
| `gifs/file-explorer-and-archives.gif` | Browse panel, archive peek |
| `gifs/ai-lookup-review.gif` | AI analyzer during scan |
| `gifs/security-and-space-recovery.gif` | Malware heuristics, space recovery |

## Adding files to the repo

1. Place stills under `screenshots/` and MP4s under `videos/` using the exact names in [ASSETS.md](ASSETS.md).
2. Run `python scripts/build_doc_gifs.py` to regenerate GIFs and sync Help tab assets.
3. Re-open [README.md](../../README.md) — image and GIF tags already point at these paths.

## Related documentation

- [User Guide](../USER_GUIDE.md) — day-to-day workflows
- [Feature Guide](../FEATURE_GUIDE.md) — scan phases and reports
- [Testing Guide](../TESTING.md) — smoke-test checklist for captures
