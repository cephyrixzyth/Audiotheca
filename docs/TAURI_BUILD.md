# Audiotheca — Tauri Desktop Build

Native Windows app with **bundled Python sidecars** — end users do not need Python installed.

For day-to-day use without building an installer, prefer the **browser UI**: `.\start-ui.ps1` (Node.js + Python only, no Rust).

| Sidecar | Role |
| --- | --- |
| `api-server.exe` | FastAPI report viewer + scan job API (port 8787) |
| `audiotheca-engine.exe` | Full scan engine (`main.py`) spawned for UI dry-runs |

## Prerequisites (maintainers only)

| Tool | Install |
| --- | --- |
| **Rust** | [rustup.rs](https://rustup.rs/) |
| **Node.js 20+** | [nodejs.org](https://nodejs.org/) |
| **Python 3.11+** | For building sidecars + engine development |

```powershell
pip install fastapi uvicorn pyinstaller
pip install -r requirements.txt
```

## One-time setup

```powershell
cd audiotheca
python scripts/setup_tauri_icons.py
cd ui
npm install
cargo tauri icon src-tauri/icons/icon.png
```

## Build sidecars (required before release)

```powershell
cd audiotheca
python scripts/build_sidecars.py
```

Produces:

```
ui/src-tauri/binaries/api-server-x86_64-pc-windows-msvc.exe
ui/src-tauri/binaries/audiotheca-engine-x86_64-pc-windows-msvc.exe
```

`npm run tauri:build` runs this automatically.

First engine build may take several minutes (~100+ MB binary with pefile/rapidfuzz).

## Development

**Quick launch** (from repo root):

```powershell
.\start-tauri.ps1
```

Checks Rust, Node.js, and icons; runs `npm run tauri:dev`.

**With system Python** (no sidecars needed):

```powershell
cd ui
npm run tauri:dev
```

Falls back to `python -m api.server` if sidecars are missing.

**With sidecars** (matches release):

```powershell
python scripts/build_sidecars.py
cd ui
npm run tauri:dev
```

## Release build

```powershell
cd ui
npm run tauri:build
```

Installer:

```
ui/src-tauri/target/release/bundle/
  msi/Audiotheca_0.2.0_x64_en-US.msi
  nsis/Audiotheca_0.2.0_x64-setup.exe
```

Sidecars are embedded in the app bundle automatically via `externalBin`.

## Runtime layout (release)

The app needs a **data directory** for reports and scan cache. Tauri sets `AUDIOTHECA_HOME` to the repo/workspace folder on dev; for end users:

```
Audiotheca/
  Audiotheca.exe              # installer puts this in Program Files
  api-server-...exe           # bundled (embedded)
  audiotheca-engine-...exe    # bundled (embedded)
  dedupe_reports/             # created on first scan (user-writable location)
```

### Recommended: portable data folder

Ship or create a user data folder and set at launch (shortcut target):

```powershell
$env:AUDIOTHECA_HOME = "$env:LOCALAPPDATA\Audiotheca"
```

The sidecar reads/writes `AUDIOTHECA_HOME\dedupe_reports\` and `decisions\`.

Copy `vendor_db.py` is embedded in engine sidecar — no separate files required for scanning.

## How spawning works

```
Audiotheca.exe (Tauri)
  └─ spawns api-server sidecar
       AUDIOTHECA_HOME = workspace
       AUDIOTHECA_ENGINE = path to audiotheca-engine sidecar
       └─ on UI "Start scan", spawns audiotheca-engine --dry-run --root Z:\...
```

## Native features

- **Open in Explorer** — `revealItemInDir` (Tauri opener plugin)
- **API** — `http://127.0.0.1:8787`
- **Scan progress** — WebSocket `ws://127.0.0.1:8787/api/jobs/{id}/events`

## Troubleshooting

| Issue | Fix |
| --- | --- |
| `cargo` not found | Install Rust via rustup — or use `.\start-ui.ps1` for browser UI |
| `npm` not found | Install Node.js; restart terminal |
| Path with spaces fails | Quote: `cd "C:\Users\...\audiotheca"` |
| Sidecar build fails | `pip install pyinstaller`; run from repo root |
| API won't start in dev | `pip install fastapi uvicorn` or build sidecars |
| Blank window | Open `http://127.0.0.1:8787/api/health` |
| Scan fails in release | Ensure `AUDIOTHECA_HOME` is writable; map `Z:` first |
| Engine sidecar huge | Expected — includes full scan stack |

See also [Quick User Guide](USER_GUIDE.md).
