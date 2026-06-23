"""
Build PyInstaller sidecars for the Tauri desktop app.

Outputs (Windows x64):
  ui/src-tauri/binaries/api-server-x86_64-pc-windows-msvc.exe
  ui/src-tauri/binaries/audiotheca-engine-x86_64-pc-windows-msvc.exe

Requires: pip install pyinstaller
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "sidecars"
WORK = ROOT / "build" / "sidecars-work"
SPEC = ROOT / "build" / "specs"
BIN_DIR = ROOT / "ui" / "src-tauri" / "binaries"

UVICORN_HIDDEN = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

API_HIDDEN = [
    "api",
    "api.server",
    "api.report_loader",
    "api.job_runner",
    "api.decisions",
    "api.models",
    "api.paths",
    "api.duplicate_execute",
    "audiotheca",
    "audiotheca.config",
    "audiotheca.engine",
    "audiotheca.helpers",
    "duplicate_feedback",
    "restructure_feedback",
    "feedback_export",
    "starlette",
    "pydantic",
    "email_validator",
    *UVICORN_HIDDEN,
]

ENGINE_HIDDEN = [
    "audiotheca",
    "audiotheca.config",
    "audiotheca.engine",
    "audiotheca.helpers",
    "audiotheca.optional_deps",
    "audiotheca.identify",
    "audiotheca.scan",
    "audiotheca.dedupe",
    "audiotheca.routing",
    "audiotheca.reports",
    "audiotheca.archive",
    "audiotheca.vendor_overrides",
    "archive_peek",
    "progress",
    "vendor_db",
    "duplicate_feedback",
    "investigation_feedback",
    "restructure_feedback",
    "pefile",
    "rapidfuzz",
    "tqdm",
    "zipfile",
    "concurrent.futures",
]


def target_triple() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "x86_64-pc-windows-msvc"
    if system == "darwin":
        return "aarch64-apple-darwin" if machine == "arm64" else "x86_64-apple-darwin"
    return "x86_64-unknown-linux-gnu"


def run_pyinstaller(name: str, entry: Path, hidden: list[str], *, console: bool = True) -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    SPEC.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(entry),
        "--onefile",
        "--name",
        name,
        "--distpath",
        str(BUILD),
        "--workpath",
        str(WORK),
        "--specpath",
        str(SPEC),
        "--paths",
        str(ROOT),
        "--clean",
        "--noconfirm",
    ]
    if console:
        cmd.append("--console")
    for module in hidden:
        cmd.extend(["--hidden-import", module])

    print(f"\n=== Building {name} ===")
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    built = BUILD / f"{name}.exe" if platform.system() == "Windows" else BUILD / name
    if not built.is_file():
        raise FileNotFoundError(f"PyInstaller did not produce {built}")
    return built


def install_to_binaries(name: str, built: Path) -> Path:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    triple = target_triple()
    suffix = ".exe" if platform.system() == "Windows" else ""
    dest = BIN_DIR / f"{name}-{triple}{suffix}"
    shutil.copy2(built, dest)
    print(f"Installed {dest} ({dest.stat().st_size / (1024 * 1024):.1f} MB)")
    return dest


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not installed. Run: pip install pyinstaller")
        return 1

    api_built = run_pyinstaller("api-server", ROOT / "scripts/api_server_entry.py", API_HIDDEN)
    engine_built = run_pyinstaller(
        "audiotheca-engine",
        ROOT / "scripts/engine_entry.py",
        ENGINE_HIDDEN,
    )

    install_to_binaries("api-server", api_built)
    install_to_binaries("audiotheca-engine", engine_built)
    print("\nSidecars ready for: npm run tauri:build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
