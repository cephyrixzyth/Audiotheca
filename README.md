# Audiotheca

**Audio Library Dedupe & Routing Engine** — scan, classify, deduplicate, and reorganize large VST/sample/installer libraries on local or network shares.

Current engine version: **9.6.0**

## What it does

Audiotheca walks your audio software root (for example `Z:\_software\_audio`), identifies vendors and products, flags duplicates and structural issues, and produces detailed reports before any files are moved. Live runs support per-section or per-item approval.

## Quick start

```powershell
cd audiotheca
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Edit config in main.py (ROOT_DIR, DRY_RUN), then:
$env:PYTHONUNBUFFERED=1
python main.py
```

Always run with `DRY_RUN = True` first and review reports in `dedupe_reports/`.

## Documentation

| Guide | Description |
| --- | --- |
| [Install Guide](docs/INSTALL.md) | Requirements, setup, configuration |
| [Feature Guide](docs/FEATURE_GUIDE.md) | Capabilities, phases, reports, folders |
| [FAQ](docs/FAQ.md) | Common questions and decisions |
| [Debug Runbook](docs/DEBUG_RUNBOOK.md) | Troubleshooting failed or suspicious runs |
| [Architecture & UI Roadmap](docs/ARCHITECTURE_AND_UI_ROADMAP.md) | UI plans, language strategy, phased build |

## Project layout

```
audiotheca/
├── main.py           # Engine entry point
├── vendor_db.py      # Vendor keyword database (~700+ vendors)
├── dedupe_reports/   # Generated CSV/Markdown reports (gitignored)
├── docs/             # Documentation
└── requirements.txt
```

## Safety defaults

- **DRY_RUN** is on by default — no filesystem changes until you disable it
- Duplicate deletes go to **`_delete-canidates`**, not permanent deletion
- Scene wrapper flattening never orphans sibling files
- Network share scans use depth limits to avoid SMB timeouts

## License

Private / internal use unless otherwise specified.
