"""Optional acoustic fingerprinting via Chromaprint fpcalc."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

FPCALC_TIMEOUT_S = 45
AUDIO_EXTS = frozenset({".wav", ".flac", ".aiff", ".aif", ".mp3", ".ogg"})


def find_fpcalc() -> Path | None:
    env = os.environ.get("FPCALC_PATH", "").strip()
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    found = shutil.which("fpcalc")
    return Path(found) if found else None


def fingerprint_file(path: Path, *, duration: int = 120) -> dict[str, Any]:
    """Return Chromaprint fingerprint for an audio file, or error metadata."""
    fpcalc = find_fpcalc()
    if fpcalc is None:
        return {"ok": False, "error": "fpcalc not found — install Chromaprint or set FPCALC_PATH"}

    if path.suffix.lower() not in AUDIO_EXTS:
        return {"ok": False, "error": f"unsupported extension: {path.suffix}"}

    try:
        proc = subprocess.run(
            [str(fpcalc), "-json", "-length", str(duration), str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=FPCALC_TIMEOUT_S,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"fpcalc timed out ({FPCALC_TIMEOUT_S}s)"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return {"ok": False, "error": err[:200] or f"fpcalc exit {proc.returncode}"}

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid fpcalc JSON output"}

    return {
        "ok": True,
        "fingerprint": payload.get("fingerprint"),
        "duration": payload.get("duration"),
        "path": str(path),
    }
