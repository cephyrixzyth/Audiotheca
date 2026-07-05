"""HASH-EXT: multi-algorithm file hash verification."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

CHUNK = 1024 * 1024


def _read_chunks(path: Path):
    with path.open("rb") as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            yield block


def hash_file(path: Path, *, algorithms: tuple[str, ...] = ("md5", "sha1", "sha256")) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "error": "not_a_file", "hashes": {}}

    digests = {name: hashlib.new(name) for name in algorithms if name in hashlib.algorithms_available}
    try:
        for block in _read_chunks(path):
            for digest in digests.values():
                digest.update(block)
    except OSError as exc:
        return {"path": str(path), "error": str(exc), "hashes": {}}

    hashes = {name: dig.hexdigest() for name, dig in digests.items()}
    blake3 = _blake3_file(path)
    if blake3:
        hashes["blake3"] = blake3

    return {"path": str(path), "size": path.stat().st_size, "hashes": hashes, "error": None}


def _blake3_file(path: Path) -> str | None:
    try:
        import blake3
    except ImportError:
        return None
    try:
        return blake3.blake3(path.read_bytes()).hexdigest()
    except (OSError, MemoryError):
        hasher = blake3.blake3()
        try:
            for block in _read_chunks(path):
                hasher.update(block)
        except OSError:
            return None
        return hasher.hexdigest()
