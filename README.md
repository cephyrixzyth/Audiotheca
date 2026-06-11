# Audiotheca

**Audio Library Dedupe & Routing Engine** — scan, classify, peek inside archives, deduplicate, and reorganize large VST/sample/installer libraries on local or network shares.

Current engine version: **9.7.0**

## What it does

Audiotheca walks your audio software root (for example `Z:\_software\_audio`), identifies vendors and products, **lists archive contents without extracting**, diagnoses scene-hash multipart sets, flags duplicates and structural issues, and produces detailed reports before any files are moved. Live runs support per-section or per-item approval with **per-phase ETA** in the terminal.

## Quick start

```powershell
cd audiotheca
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Install 7-Zip for .rar/.7z archive listing (required for archive peek)
# https://www.7-zip.org/

# Edit config in main.py (ROOT_DIR, DRY_RUN), then:
$env:PYTHONUNBUFFERED=1
python main.py
```

Always run with `DRY_RUN = True` first and review reports in `dedupe_reports/`.

Re-peek archives from the last coexistence CSV without a full scan:

```powershell
python peek_archives.py
```

Run unit tests:

```powershell
python -m pytest tests/ -q
```

## Documentation

| Guide | Description |
| --- | --- |
| [Install Guide](docs/INSTALL.md) | Requirements, 7-Zip, setup, configuration |
| [Feature Guide](docs/FEATURE_GUIDE.md) | Phases, archive peek, scene rename, reports |
| [FAQ](docs/FAQ.md) | Common questions and decisions |
| [Debug Runbook](docs/DEBUG_RUNBOOK.md) | Troubleshooting, multipart archives, hung scans |
| [Changelog](docs/CHANGELOG.md) | Version history |
| [Architecture & UI Roadmap](docs/ARCHITECTURE_AND_UI_ROADMAP.md) | Future UI plans |

## Project layout

```
audiotheca/
├── main.py              # Engine entry point
├── archive_peek.py      # Archive listing, scene identity, multipart diagnostics
├── progress.py          # Phase progress + ETA helpers
├── peek_archives.py     # Standalone archive peek CLI
├── vendor_db.py         # Vendor keyword database (~700+ vendors)
├── tests/               # pytest unit tests
├── dedupe_reports/      # Generated CSV/Markdown reports (gitignored)
├── docs/                # Documentation
└── requirements.txt
```

## Safety defaults

- **DRY_RUN** is on by default — no filesystem changes until you disable it
- Duplicate deletes go to **`_delete-canidates`**, not permanent deletion
- Scene auto-rename is opt-in via `SCENE_AUTO_RENAME` but still respects dry-run
- Network share scans use depth limits to avoid SMB timeouts

## License

Private / internal use unless otherwise specified.
