"""Content hashing helpers — sparse, full, and rolling-hash sidecar integration."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

FULL_HASH_MAX_BYTES = 200 * 1024 * 1024  # 200 MB
_HASH_CHUNK = 1024 * 1024  # 1 MB read chunks


def sparse_hash(filepath: str | Path, chunk_size: int = 4096) -> str | None:
    """MD5 of head, middle, and tail chunks — cheap content fingerprint over SMB."""
    hasher = hashlib.md5()
    try:
        file_size = os.path.getsize(filepath)
        with open(filepath, "rb") as handle:
            hasher.update(handle.read(chunk_size))
            if file_size > chunk_size * 3:
                handle.seek(file_size // 2)
                hasher.update(handle.read(chunk_size))
                handle.seek(file_size - chunk_size)
                hasher.update(handle.read(chunk_size))
        return hasher.hexdigest()
    except OSError:
        return None


def full_hash(filepath: str | Path, *, max_bytes: int = FULL_HASH_MAX_BYTES) -> str | None:
    """Full-file MD5 for files under ``max_bytes``; None if too large or unreadable."""
    try:
        file_size = os.path.getsize(filepath)
    except OSError:
        return None
    if file_size > max_bytes:
        return None
    hasher = hashlib.md5()
    try:
        with open(filepath, "rb") as handle:
            remaining = file_size
            while remaining > 0:
                chunk = handle.read(min(_HASH_CHUNK, remaining))
                if not chunk:
                    break
                hasher.update(chunk)
                remaining -= len(chunk)
        return hasher.hexdigest()
    except OSError:
        return None


def content_hash(filepath: str | Path, *, prefer_full: bool = True) -> str | None:
    """Best available hash: full for small files, rolling sidecar or sparse for large."""
    path = Path(filepath)
    try:
        file_size = os.path.getsize(path)
    except OSError:
        return None

    if prefer_full and file_size <= FULL_HASH_MAX_BYTES:
        digest = full_hash(path)
        if digest:
            return digest

    from audiotheca.sidecar_tools import rolling_hash_file

    sidecar = rolling_hash_file(path)
    if sidecar.get("ok") and sidecar.get("hash"):
        return str(sidecar["hash"])

    return sparse_hash(path)
