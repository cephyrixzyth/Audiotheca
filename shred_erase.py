"""SHRED-ERASE: multi-pass secure file erasure."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def secure_delete(path: str | Path, *, passes: int = 3) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        return {"path": str(target), "deleted": False, "error": "not_a_file"}
    size = target.stat().st_size
    try:
        with target.open("r+b") as handle:
            for i in range(max(1, passes)):
                handle.seek(0)
                handle.write(os.urandom(size))
                handle.flush()
                os.fsync(handle.fileno())
        target.unlink()
    except OSError as exc:
        return {"path": str(target), "deleted": False, "error": str(exc)}
    return {"path": str(target), "deleted": True, "passes": passes, "bytes": size}
