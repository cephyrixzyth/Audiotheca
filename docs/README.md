# Audiotheca documentation index

Start with the [main README](../README.md) for overview, quick start, UI tour, and media placeholders.

Engine **10.0.0** · Web UI **1.0.2**

---

## Guides by goal

| I want to… | Read |
|------------|------|
| **Get oriented (new user)** | [Main README](../README.md) |
| **Test on my own PC** | [TESTING.md](TESTING.md) |
| Use the app day to day | [USER_GUIDE.md](USER_GUIDE.md) |
| Install Python, 7-Zip, Node | [INSTALL.md](INSTALL.md) |
| Set library path & env vars | [CONFIGURATION.md](CONFIGURATION.md) |
| Understand scan phases & reports | [FEATURE_GUIDE.md](FEATURE_GUIDE.md) |
| Fix problems | [DEBUG_RUNBOOK.md](DEBUG_RUNBOOK.md) · [FAQ.md](FAQ.md) |
| API security & tokens | [SECURITY.md](SECURITY.md) |
| Build desktop installer | [TAURI_BUILD.md](TAURI_BUILD.md) |
| Architecture & roadmap | [ARCHITECTURE_AND_UI_ROADMAP.md](ARCHITECTURE_AND_UI_ROADMAP.md) |
| **94-code spec catalog** | [SPEC_CATALOG.md](SPEC_CATALOG.md) |
| Add doc screenshots/videos | [assets/README.md](assets/README.md) · [assets/ASSETS.md](assets/ASSETS.md) |
| Deploy on Unraid Docker | [../deploy/unraid/README.md](../deploy/unraid/README.md) |
| Optional web search helper | [../docker/searxng/README.md](../docker/searxng/README.md) |
| Version history | [CHANGELOG.md](CHANGELOG.md) |

---

## Quick path for external testers

1. Clone repo → `pip install -r requirements.txt`
2. Copy [../.env.example](../.env.example) → set `AUDIOTHECA_LIBRARY_ROOT`
3. `python -m pytest tests/ -q`
4. Temp-folder smoke test → [TESTING.md §3](TESTING.md#3-point-at-your-library-not-the-authors)
5. `.\start-ui.ps1` → http://localhost:5173
6. Optional: capture screenshots per [assets/ASSETS.md](assets/ASSETS.md)

---

## Web UI tabs (reference)

Help appears **last** in the tab bar. Full descriptions: [User guide — Web UI tabs](USER_GUIDE.md#web-ui-tabs).

Dashboard · Scan · Investigation · Duplicates · Restructure · Archives · Scene renames · Scan audit · Skipped files · Space recovery · Security · Environment · Vendors · **Help**
