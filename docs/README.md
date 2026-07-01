# Audiotheca documentation index

Start with the guide that matches your goal:

| I want to… | Read |
|------------|------|
| **Test on my own PC / new user** | [TESTING.md](TESTING.md) |
| Use the app day to day | [USER_GUIDE.md](USER_GUIDE.md) |
| Install Python, 7-Zip, Node | [INSTALL.md](INSTALL.md) |
| Set library path & env vars | [CONFIGURATION.md](CONFIGURATION.md) |
| Understand scan phases & reports | [FEATURE_GUIDE.md](FEATURE_GUIDE.md) |
| Fix problems | [DEBUG_RUNBOOK.md](DEBUG_RUNBOOK.md) · [FAQ.md](FAQ.md) |
| API security & tokens | [SECURITY.md](SECURITY.md) |
| Build desktop installer | [TAURI_BUILD.md](TAURI_BUILD.md) |
| Deploy on Unraid Docker | [../deploy/unraid/README.md](../deploy/unraid/README.md) |
| Optional web search helper | [../docker/searxng/README.md](../docker/searxng/README.md) |
| Version history | [CHANGELOG.md](CHANGELOG.md) |

**Quick paths for external testers**

1. Clone repo → `pip install -r requirements.txt`
2. Copy [../.env.example](../.env.example) → set `AUDIOTHECA_LIBRARY_ROOT`
3. `python -m pytest tests/ -q`
4. Temp-folder smoke test → [TESTING.md §3](TESTING.md#3-point-at-your-library-not-the-authors)
5. `.\start-ui.ps1` → http://localhost:5173
