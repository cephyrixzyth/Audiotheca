"""SHRED-ERASE: multi-pass secure file erasure."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

MAX_PASSES = 7
CHUNK_BYTES = 4 * 1024 * 1024

# Filesystems where overwriting in place writes new blocks (copy-on-write) or
# where the device remaps writes, so the old bytes are not reliably destroyed.
_COW_FILESYSTEMS = frozenset({"btrfs", "zfs", "apfs", "bcachefs", "refs", "f2fs", "nilfs2"})


def _filesystem_type(path: Path) -> str:
    """Best-effort filesystem name for *path* ("" when unknown)."""
    if sys.platform.startswith("linux"):
        try:
            target = str(path.resolve())
            best = ("", "")
            with open("/proc/self/mounts", encoding="utf-8") as handle:
                for line in handle:
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    mount = parts[1].replace("\\040", " ")
                    if (target == mount or target.startswith(mount.rstrip("/") + "/")) and len(mount) > len(best[0]):
                        best = (mount, parts[2])
            return best[1].lower()
        except OSError:
            return ""
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["/usr/bin/stat", "-f", "%T", str(path)], capture_output=True, text=True, timeout=5)
            return out.stdout.strip().lower()
        except (OSError, subprocess.SubprocessError):
            return ""
    return ""


def secure_delete(path: str | Path, *, passes: int = 3) -> dict[str, Any]:
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        return {"path": str(target), "deleted": False, "error": "not_a_file"}
    passes = max(1, min(int(passes), MAX_PASSES))
    try:
        stat = target.stat()
    except OSError as exc:
        return {"path": str(target), "deleted": False, "error": str(exc)}
    if stat.st_nlink > 1:
        # Overwriting a hardlinked inode would destroy every other name for the
        # same data — including the keeper that space recovery linked it to.
        return {
            "path": str(target),
            "deleted": False,
            "error": "hardlinked",
            "detail": f"File shares its data with {stat.st_nlink - 1} other link(s); shredding would destroy them too.",
        }
    size = stat.st_size
    fs_type = _filesystem_type(target)
    try:
        with target.open("r+b") as handle:
            for _ in range(passes):
                handle.seek(0)
                remaining = size
                while remaining > 0:
                    chunk = min(CHUNK_BYTES, remaining)
                    handle.write(os.urandom(chunk))
                    remaining -= chunk
                handle.flush()
                os.fsync(handle.fileno())
        target.unlink()
    except OSError as exc:
        return {"path": str(target), "deleted": False, "error": str(exc)}
    result: dict[str, Any] = {"path": str(target), "deleted": True, "passes": passes, "bytes": size}
    if fs_type in _COW_FILESYSTEMS:
        result["erasure_guaranteed"] = False
        result["warning"] = (
            f"{fs_type} is copy-on-write: the file was deleted, but earlier copies of its "
            "blocks may survive on disk or in snapshots."
        )
    return result
