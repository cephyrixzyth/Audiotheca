#!/usr/bin/env python3
"""Build Rust native sidecars (rolling hash + parallel walk)."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / "sidecars" / "bin"
CRATES = [
    ("rolling_hash", "audiotheca-rolling-hash"),
    ("parallel_walk", "audiotheca-parallel-walk"),
]


def _cargo() -> str:
    cargo = shutil.which("cargo")
    if not cargo:
        raise RuntimeError("cargo not found — install Rust toolchain from https://rustup.rs")
    return cargo


def build_crate(crate_dir: Path, binary_name: str, *, release: bool) -> Path:
    cargo = _cargo()
    cmd = [cargo, "build", "--manifest-path", str(crate_dir / "Cargo.toml")]
    if release:
        cmd.append("--release")
    print(f"=== Building {binary_name} ===")
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    profile = "release" if release else "debug"
    built = crate_dir / "target" / profile / binary_name
    if platform.system() == "Windows":
        built = built.with_suffix(".exe")
    if not built.is_file():
        raise FileNotFoundError(f"Expected {built}")
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Audiotheca Rust sidecars")
    parser.add_argument("--release", action="store_true", help="Release build (optimized)")
    args = parser.parse_args()

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ".exe" if platform.system() == "Windows" else ""

    for crate_name, binary_name in CRATES:
        crate_dir = ROOT / "sidecars" / crate_name
        built = build_crate(crate_dir, binary_name, release=args.release)
        dest = BIN_DIR / f"{binary_name}{suffix}"
        shutil.copy2(built, dest)
        print(f"Installed {dest}")

    print("\nSidecars ready. Set AUDIOTHECA_ROLLING_HASH_PATH / AUDIOTHECA_PARALLEL_WALK_PATH or use sidecars/bin/")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
