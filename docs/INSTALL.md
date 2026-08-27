# Audiotheca — Install Guide

Engine version: **10.0.0** · Web UI: **1.0.12**

For overview and first-run walkthrough, see the [main README](../README.md).

For a step-by-step **first run on another machine**, see **[Testing Guide](TESTING.md)**.

---

## Pre-built installers

End users do **not** need Python, Node, or Rust when using release installers — the Tauri app bundles API + engine sidecars.

**Download:** [GitHub Releases (latest)](https://github.com/chrisjrovira/Audiotheca/releases/latest) — Windows `.msi`, NSIS setup, portable zip; macOS `.dmg` (Intel + Apple Silicon); Linux `.AppImage` and `.deb` (built on each release tag via GitHub Actions).

**No GitHub Actions quota?** Build locally:

| Platform | Command |
| --- | --- |
| Windows | `.\scripts\package-local-release.ps1 -Tag v1.0.12` |
| Linux (Docker on Windows) | `.\scripts\build-linux-docker.ps1` |
| macOS (M4 / Intel Mac) | `./scripts/build-release-mac.sh --both` |
| Stage all | `.\scripts\stage-local-release.ps1 -Tag v1.0.12 -Merge` |

Artifacts land in `dist/releases/<tag>/` (see `dist/releases/README.md`).

| Platform | Build script (maintainers) | Output folder | Artifacts |
| --- | --- | --- | --- |
| **Windows** | `.\scripts\build-installers.ps1` or `.\scripts\package-local-release.ps1` | `dist/installers/windows/` and `dist/releases/<tag>/` | `.msi`, NSIS `-setup.exe` |
| **Windows portable** | `.\scripts\build-portable.ps1` | `dist/installers/windows/` | `Audiotheca-Portable-<version>-win64.zip` |
| **macOS** | `./scripts/build-installers.sh` | `dist/installers/mac/` | `.dmg` |
| **Linux** | `./scripts/build-installers.sh` | `dist/installers/linux/` | `.AppImage`, `.deb` |

### Windows installer

1. Download or build `Audiotheca_1.0.12_x64_en-US.msi` or `Audiotheca_1.0.12_x64-setup.exe` from [GitHub Releases](https://github.com/chrisjrovira/Audiotheca/releases/latest).
2. **Close Audiotheca completely** before upgrading (including any background API sidecar).
3. Run the installer as Administrator — WebView2 bootstrapper is included when needed.
4. Launch **Audiotheca** from the Start menu; use the first-run wizard to set your library root.

### Upgrading on Windows (fix “error opening file for writing”)

The desktop app spawns **api-server** and **audiotheca-engine** sidecars. If they stay running, the NSIS/MSI installer cannot overwrite files under `Program Files`.

1. Quit **Audiotheca** from the taskbar (not only the window — exit the app).
2. Open Task Manager → end any **`Audiotheca`**, **`api-server`**, or **`audiotheca-engine`** processes.
3. Or run: `powershell -ExecutionPolicy Bypass -File scripts\kill-audiotheca.ps1`
4. Re-run the installer **as Administrator**.

Installers built from 1.0.5+ include NSIS hooks that terminate these processes automatically before copying files.

### Windows portable zip

1. Extract `Audiotheca-Portable-1.0.12-win64.zip` to any writable folder.
2. Double-click **`Run Audiotheca.bat`** (no terminal window).
3. Reports and cache go in `data/` (`portable.json` documents `AUDIOTHECA_HOME` relative to the exe).

### macOS (Apple Silicon M1–M4 and Intel)

1. Download the correct `.dmg` from [GitHub Releases](https://github.com/chrisjrovira/Audiotheca/releases/latest):
   - **Apple Silicon (M1–M4):** `*_aarch64.dmg` or `*_arm64.dmg`
   - **Intel Mac:** `*_x64.dmg` or `*_x86_64.dmg`
2. Open the DMG and drag **Audiotheca** into **Applications**.
3. **First launch:** right-click **Audiotheca** in Applications → **Open** → confirm **Open** (unsigned download from GitHub).
4. If **nothing happens** when double-clicking (no window, no dialog):
   ```bash
   cd /path/to/audiotheca   # optional: repo checkout
   ./scripts/macos_fixup_app.sh /Applications/Audiotheca.app
   ```
   Or manually:
   ```bash
   xattr -dr com.apple.quarantine /Applications/Audiotheca.app
   codesign --force --deep --sign - /Applications/Audiotheca.app
   ```
   Then right-click → **Open** again.
5. **Diagnostics:** startup log at  
   `~/Library/Application Support/com.audiotheca.desktop/audiotheca-desktop.log`  
   Crash reports: **Console.app** → search `Audiotheca`.

App data (reports, cache) is stored under `~/Library/Application Support/com.audiotheca.desktop/` — not inside the read-only `.app` bundle.

### Linux

- **Linux AppImage:** `chmod +x Audiotheca_*.AppImage && ./Audiotheca_*.AppImage`
- **Linux deb:** `sudo dpkg -i audiotheca_*.deb`

For portable-style data on macOS/Linux, set `AUDIOTHECA_HOME` to a writable folder before launch.

---

## Requirements (manual / CLI path)

| Requirement | Notes |
| --- | --- |
| **Python** | 3.11+ (3.13 recommended) |
| **OS** | Windows (primary); Linux possible for engine/API with path adjustments |
| **Storage** | Local disk or SMB/CIFS mapped drive |
| **7-Zip** | **Required for archive peek** (`.rar`, `.7z`, `.iso`) — [7-zip.org](https://www.7-zip.org/) |
| **Node.js 24+** | Browser UI only — [nodejs.org](https://nodejs.org/) (Active LTS) |
| **Rust** | Tauri desktop builds only — [rustup.rs](https://rustup.rs/) |
| **Write access** | Live runs only (`DRY_RUN = False` or `--live`) |

### Python packages

```powershell
pip install -r requirements.txt
```

| Package | Purpose |
| --- | --- |
| `pefile` | PE `CompanyName` vendor ID + capability hints |
| `rapidfuzz` | Fuzzy duplicate name matching |
| `mutagen` | WAV/FLAC/AIFF/MP3 tag I/O (Phase M3) |
| `numpy` / `pyloudnorm` | ITU-R BS.1770 integrated loudness (RMS proxy if missing) |
| `tqdm` | Scan progress bar with ETA |
| `psutil` | CPU/RAM metrics in Dashboard (optional) |
| `fastapi` / `uvicorn` | Local API for web UI |
| `pytest` / `httpx` | Unit tests |
| `pyinstaller` | Sidecar builds (maintainers) |

---

## Installation

```powershell
cd "C:\path\to\audiotheca"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Verify:

```powershell
python -c "import pefile; import rapidfuzz; import tqdm; import mutagen; import pyloudnorm; print('OK')"
where.exe 7z
python -c "from archive_peek import find_7z; print(find_7z())"
python -m pytest tests/ -q
```

Optional — Node.js for UI:

```powershell
node --version
cd ui && npm install
```

---

## Configuration

**Do not use the author's default path.** Set your library root before scanning:

```powershell
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
$env:AUDIOTHECA_LIBRARY_ROOTS = $env:AUDIOTHECA_LIBRARY_ROOT
```

Or copy [.env.example](../.env.example) → `.env` and edit paths.

Full reference: **[Configuration](CONFIGURATION.md)**

### Engine (code or CLI)

```powershell
python main.py --dry-run --root "D:\YourLibrary\_software\_audio"
python main.py --live --root "D:\YourLibrary\_software\_audio"
```

Key settings in `audiotheca/config.py`:

| Setting | Default | Notes |
| --- | --- | --- |
| `DRY_RUN` | `True` | Safe default |
| `MAX_WORKERS` | `8` | Use 4–8 on SMB |
| `MAX_WALK_DEPTH` / `PROBE_DEPTH` | `8` | Lower if hangs |
| `ENABLE_ARCHIVE_PEEK` | `True` | Needs 7-Zip |
| `SCENE_AUTO_RENAME` | `False` | Stage 2 |
| `ACTION_MODE` | `section` | Live approval granularity |

### Staged live rollout

| Stage | Settings | Action |
| --- | --- | --- |
| **1** | `DRY_RUN=False`, `ACTION_MODE=section`, `SCENE_AUTO_RENAME=False` | Restructure + investigation routing |
| **2** | `SCENE_AUTO_RENAME=True`, `ACTION_MODE=item` | Scene-hash renames |
| **3** | — | `move_redundant_archives_{stamp}.ps1` |
| **4** | — | Duplicate staging via UI |

Bump `CACHE_SCHEMA` only when scan tree output format changes.

---

## Running

### Engine

```powershell
$env:PYTHONUNBUFFERED = "1"
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
python main.py --dry-run
```

Reports: `dedupe_reports/` (or `$AUDIOTHECA_HOME/dedupe_reports/`).

### Web UI

```powershell
$env:AUDIOTHECA_LIBRARY_ROOT = "D:\YourLibrary\_software\_audio"
.\start-ui.ps1          # API + browser
.\start-api.ps1         # API only
```

Manual:

```powershell
python -m api.server
# separate terminal:
cd ui && npm run dev
```

UI: http://localhost:5173 · API health: http://127.0.0.1:8787/api/health

**In-app dependency install:** open the **Environment** tab → **Install missing dependencies** (pip packages; bundled 7-Zip on Windows). Live install requires confirmation (`confirm_live: true`). Manual fallback: `pip install -r requirements.txt` and install 7-Zip from [7-zip.org](https://www.7-zip.org/).

Non-default API port:

```powershell
$env:AUDIOTHECA_API_PORT = "8790"
$env:VITE_API_PORT = "8790"
```

### Utilities

```powershell
python peek_archives.py
python gen_archive_delete_candidates.py dedupe_reports\Archive_Peek_*.csv
python space_recovery.py --root "D:\YourLibrary\_software\_audio" --no-links
python scripts/library_probe.py
```

---

## Optional: Rust native sidecars

Rolling-hash and parallel-walk accelerators live under `sidecars/`. Binaries are **not** committed — build locally when needed:

```powershell
python scripts/build_native_sidecars.py --release
```

Output: `sidecars/bin/audiotheca-rolling-hash.exe` and `audiotheca-parallel-walk.exe` (no extension on Linux/macOS).

The engine auto-discovers these paths, or set:

- `AUDIOTHECA_ROLLING_HASH_PATH`
- `AUDIOTHECA_PARALLEL_WALK_PATH`

Requires [Rust](https://rustup.rs/) (`cargo` on PATH). Tauri desktop builds use a separate PyInstaller sidecar pipeline (`scripts/build_sidecars.py`).

---

## Optional: DAW sidecar plugin (JUCE)

The **Environment → DAW sidecar plugin** panel exports a JUCE scaffold (spec **DAW-SIDE**). Full VST3/AU builds need CMake 3.22+, a C++17 compiler, and JUCE 7 — too heavy for CI.

1. Export blueprint from the UI (or `POST /api/tools/daw-side/blueprint`).
2. Build with the generated `build.ps1` / `build.sh` in the export folder, or from repo template:
   - Windows: `.\scripts\build_daw_sidecar.ps1`
   - Linux/macOS: `./scripts/build_daw_sidecar.sh`
3. Copy the VST3 from `build/AudiothecaSidecar_artefacts/VST3/` into your DAW plugin folder and rescan.

---

## Performance (network shares)

| Setting | Recommendation |
| --- | --- |
| `MAX_WORKERS` | 4–8 |
| `MAX_WALK_DEPTH` | 5–8 if scans hang |
| `PYTHONUNBUFFERED` | Always `1` |
| Cache | Keep `scan_cache.json` between runs; delete after `CACHE_SCHEMA` bump |

---

## Live-run approval

| `ACTION_MODE` | Behavior |
| --- | --- |
| `ask` | Prompt at start |
| `section` | Approve each category bin |
| `item` | Confirm every action |
| `auto` | No prompts (use with care) |

---

## First live run checklist

1. Successful dry run with 10.0.0 header
2. Review `Scene_Rename_Plan_*.csv` and `Archive_Peek_*.csv`
3. Check `Multipart_Archive_Diagnostic_*.csv` for `MISSING_PART01`
4. **Backup library**
5. Stage 1: `ACTION_MODE = "section"`
6. `python main.py --live` or UI execute with confirmation

See [Quick User Guide](USER_GUIDE.md) and [Testing Guide](TESTING.md).
