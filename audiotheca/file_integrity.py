"""Stable content identities for a single file or a complete directory tree."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path


def _signature(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def content_identity(path: Path) -> str:
    """Include relative paths and empty directories. Fail closed on links or concurrent edits."""
    digest = hashlib.sha256()

    def visit(item: Path, relative: str) -> None:
        start = item.lstat()
        if stat.S_ISDIR(start.st_mode):
            record = [relative, "dir"]
        elif stat.S_ISREG(start.st_mode):
            with item.open("rb") as stream:
                if _signature(os.fstat(stream.fileno())) != _signature(start):
                    raise ValueError(f"File changed before read: {item}")
                file_hash = hashlib.file_digest(stream, "sha256").hexdigest()
                if _signature(os.fstat(stream.fileno())) != _signature(start):
                    raise ValueError(f"File changed during read: {item}")
            record = [relative, "file", start.st_size, file_hash]
        else:
            raise ValueError(f"Cannot verify special file or link: {item}")
        digest.update(json.dumps(record, ensure_ascii=True).encode("ascii") + b"\n")
        if stat.S_ISDIR(start.st_mode):
            for child in sorted(item.iterdir(), key=lambda p: p.name):
                visit(child, f"{relative}/{child.name}")
        if _signature(start) != _signature(item.lstat()):
            raise ValueError(f"Object changed during verification: {item}")

    visit(path, "")
    return digest.hexdigest()
