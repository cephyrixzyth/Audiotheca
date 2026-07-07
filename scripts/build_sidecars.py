"""
Build PyInstaller sidecars for the Tauri desktop app.

Outputs (per host or --target triple), e.g. Windows x64:
  ui/src-tauri/binaries/api-server-x86_64-pc-windows-msvc.exe
  ui/src-tauri/binaries/audiotheca-engine-x86_64-pc-windows-msvc.exe

Requires: pip install pyinstaller
"""

from __future__ import annotations

import argparse
import os
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
    "api.archive_execute",
    "api.restructure_execute",
    "api.scene_execute",
    "audiotheca",
    "audiotheca.config",
    "audiotheca.engine",
    "audiotheca.helpers",
    "duplicate_feedback",
    "restructure_feedback",
    "archive_feedback",
    "scene_feedback",
    "job_control",
    "scan_options",
    "system_metrics",
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
    "job_control",
    "scan_options",
    "pefile",
    "rapidfuzz",
    "tqdm",
    "zipfile",
    "concurrent.futures",
]


def host_target_triple() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "x86_64-pc-windows-msvc"
    if system == "darwin":
        return "aarch64-apple-darwin" if machine == "arm64" else "x86_64-apple-darwin"
    return "x86_64-unknown-linux-gnu"


def resolve_target(explicit: str | None) -> str:
    if explicit:
        return explicit
    return host_target_triple()


def host_darwin_arch() -> str | None:
    if platform.system() != "Darwin":
        return None
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    return None


def darwin_arch_for_target(triple: str, explicit_arch: str | None) -> str | None:
    if platform.system() != "Darwin":
        return None
    if explicit_arch:
        return explicit_arch
    if triple.startswith("x86_64-apple-darwin"):
        return "x86_64"
    if triple.startswith("aarch64-apple-darwin"):
        return "arm64"
    return None


def needs_darwin_arch_wrapper(requested: str | None) -> bool:
    """Use arch(1) only when cross-compiling on macOS (host arch != target arch)."""
    if not requested:
        return False
    host = host_darwin_arch()
    return host is not None and host != requested


def sidecar_suffix(triple: str) -> str:
    return ".exe" if triple.endswith("-pc-windows-msvc") else ""


def run_pyinstaller(
    name: str,
    entry: Path,
    hidden: list[str],
    *,
    console: bool = True,
    darwin_arch: str | None = None,
) -> Path:
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

    if darwin_arch and needs_darwin_arch_wrapper(darwin_arch):
        # macOS arch(1) requires a leading dash: arch -arm64 / arch -x86_64
        cmd = ["arch", f"-{darwin_arch}", *cmd]

    print(f"\n=== Building {name} ===")
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    built = BUILD / f"{name}.exe" if platform.system() == "Windows" else BUILD / name
    if not built.is_file():
        raise FileNotFoundError(f"PyInstaller did not produce {built}")
    return built


def install_to_binaries(name: str, built: Path, triple: str) -> Path:
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    dest = BIN_DIR / f"{name}-{triple}{sidecar_suffix(triple)}"
    shutil.copy2(built, dest)
    if triple.endswith("-apple-darwin"):
        dest.chmod(0o755)
    print(f"Installed {dest} ({dest.stat().st_size / (1024 * 1024):.1f} MB)")
    return dest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build PyInstaller sidecars for Tauri")
    parser.add_argument(
        "--target",
        default=os.environ.get("AUDIOTHECA_TARGET") or os.environ.get("CARGO_BUILD_TARGET"),
        help="Rust target triple for sidecar naming (default: native host)",
    )
    parser.add_argument(
        "--arch",
        default=os.environ.get("AUDIOTHECA_SIDECAR_ARCH"),
        help="macOS arch for PyInstaller (arm64 or x86_64); default: infer from --target",
    )
    return parser.parse_args()


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not installed. Run: pip install pyinstaller")
        return 1

    args = parse_args()
    triple = resolve_target(args.target)
    darwin_arch = darwin_arch_for_target(triple, args.arch)
    if darwin_arch:
        if needs_darwin_arch_wrapper(darwin_arch):
            print(f"Building sidecars for target {triple} via macOS arch -{darwin_arch}")
        else:
            print(f"Building sidecars for target {triple} (native macOS {darwin_arch})")
    else:
        print(f"Building sidecars for target {triple}")

    api_built = run_pyinstaller(
        "api-server",
        ROOT / "scripts/api_server_entry.py",
        API_HIDDEN,
        darwin_arch=darwin_arch,
    )
    engine_built = run_pyinstaller(
        "audiotheca-engine",
        ROOT / "scripts/engine_entry.py",
        ENGINE_HIDDEN,
        darwin_arch=darwin_arch,
    )

    install_to_binaries("api-server", api_built, triple)
    install_to_binaries("audiotheca-engine", engine_built, triple)
    print("\nSidecars ready for: npm run tauri:build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
