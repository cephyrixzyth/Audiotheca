"""Native helper sidecars — rolling hash and parallel walk (subprocess pattern)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SIDECAR_DIR = ROOT / "sidecars" / "bin"
ROLLING_HASH_TIMEOUT_S = 120
PARALLEL_WALK_TIMEOUT_S = 300


def _sidecar_binary(name: str) -> Path | None:
    env_key = f"AUDIOTHECA_{name.upper()}_PATH"
    env = os.environ.get(env_key, "").strip()
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    suffix = ".exe" if sys.platform == "win32" else ""
    for base in (SIDECAR_DIR, ROOT / "sidecars"):
        candidate = base / f"{name}{suffix}"
        if candidate.is_file():
            return candidate
    found = shutil.which(name)
    return Path(found) if found else None


def rolling_hash_file(path: str | Path, *, algorithm: str = "md5") -> dict[str, Any]:
    """Hash a file via Rust sidecar or Python fallback."""
    target = Path(path)
    if not target.is_file():
        return {"ok": False, "error": "not a file", "path": str(target)}

    binary = _sidecar_binary("audiotheca-rolling-hash")
    if binary:
        try:
            proc = subprocess.run(
                [str(binary), "--json", str(target), "--algo", algorithm],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=ROLLING_HASH_TIMEOUT_S,
                check=False,
                shell=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                payload = json.loads(proc.stdout)
                if payload.get("ok"):
                    return payload
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
            pass

    return _rolling_hash_python(target, algorithm=algorithm)


def _rolling_hash_python(path: Path, *, algorithm: str = "md5") -> dict[str, Any]:
    import hashlib

    hasher = hashlib.new(algorithm)
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
        return {
            "ok": True,
            "path": str(path),
            "hash": hasher.hexdigest(),
            "size": size,
            "algorithm": algorithm,
            "backend": "python",
        }
    except OSError as exc:
        return {"ok": False, "error": str(exc), "path": str(path)}


def parallel_walk(
    root: str | Path,
    *,
    max_depth: int = 8,
    follow_symlinks: bool = False,
) -> dict[str, Any]:
    """Walk a directory tree via Rust sidecar or Python fallback."""
    target = Path(root)
    if not target.is_dir():
        return {"ok": False, "error": "not a directory", "root": str(target)}

    binary = _sidecar_binary("audiotheca-parallel-walk")
    if binary:
        try:
            proc = subprocess.run(
                [
                    str(binary),
                    "--json",
                    str(target),
                    "--max-depth",
                    str(max_depth),
                    "--follow-symlinks" if follow_symlinks else "--no-follow-symlinks",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=PARALLEL_WALK_TIMEOUT_S,
                check=False,
                shell=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                payload = json.loads(proc.stdout)
                if payload.get("ok"):
                    return payload
        except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
            pass

    return _parallel_walk_python(target, max_depth=max_depth, follow_symlinks=follow_symlinks)


def _parallel_walk_python(
    root: Path,
    *,
    max_depth: int,
    follow_symlinks: bool,
) -> dict[str, Any]:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    entries: list[dict[str, Any]] = []

    def _scan_dir(current: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            with os.scandir(current) as scan:
                child_dirs = []
                for entry in scan:
                    try:
                        if entry.is_file(follow_symlinks=follow_symlinks):
                            stat = entry.stat(follow_symlinks=follow_symlinks)
                            entries.append(
                                {
                                    "path": entry.path,
                                    "name": entry.name,
                                    "size": stat.st_size,
                                    "is_dir": False,
                                }
                            )
                        elif entry.is_dir(follow_symlinks=follow_symlinks):
                            child_dirs.append(Path(entry.path))
                    except OSError:
                        continue
                if depth < max_depth and child_dirs:
                    with ThreadPoolExecutor(max_workers=min(8, len(child_dirs))) as pool:
                        futures = [pool.submit(_scan_dir, child, depth + 1) for child in child_dirs]
                        for fut in as_completed(futures):
                            fut.result()
        except OSError:
            return

    _scan_dir(root, 0)
    return {
        "ok": True,
        "root": str(root),
        "count": len(entries),
        "entries": entries,
        "backend": "python",
    }
