"""Optional acoustic fingerprinting via Chromaprint (native lib or fpcalc)."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

FPCALC_TIMEOUT_S = 45
AUDIO_EXTS = frozenset({".wav", ".flac", ".aiff", ".aif", ".mp3", ".ogg"})

_libchromaprint: ctypes.CDLL | None = None


def _load_chromaprint() -> ctypes.CDLL | None:
    global _libchromaprint
    if _libchromaprint is not None:
        return _libchromaprint

    env = os.environ.get("CHROMAPRINT_LIB", "").strip()
    candidates: list[str] = []
    if env:
        candidates.append(env)
    if sys.platform == "win32":
        candidates.extend(["chromaprint.dll", "libchromaprint-1.dll"])
    elif sys.platform == "darwin":
        candidates.extend(["libchromaprint.1.dylib", "libchromaprint.dylib"])
    else:
        candidates.extend(["libchromaprint.so.1", "libchromaprint.so"])

    for name in candidates:
        try:
            _libchromaprint = ctypes.CDLL(name)
            return _libchromaprint
        except OSError:
            continue
    return None


def _fingerprint_native(path: Path, *, duration: int = 120) -> dict[str, Any]:
    """Fingerprint via libchromaprint ctypes bindings (no fpcalc subprocess)."""
    lib = _load_chromaprint()
    if lib is None:
        return {"ok": False, "error": "libchromaprint not found — set CHROMAPRINT_LIB or install Chromaprint"}

    # Prefer fpcalc for actual audio decode — native path validates library load.
    # When pyacoustid is available, use it for full native decode+fingerprint.
    try:
        import acoustid  # type: ignore[import-untyped]

        duration_s, fingerprint = acoustid.fingerprint_file(str(path))
        return {
            "ok": True,
            "fingerprint": fingerprint,
            "duration": duration_s,
            "path": str(path),
            "backend": "pyacoustid",
        }
    except ImportError:
        pass
    except Exception as exc:
        return {"ok": False, "error": f"pyacoustid failed: {exc}"}

    # Minimal ctypes probe — confirms library is loadable; defer decode to fpcalc.
    try:
        lib.chromaprint_get_version.restype = ctypes.c_char_p
        version = lib.chromaprint_get_version()
        version_str = version.decode("utf-8") if version else "unknown"
    except (AttributeError, OSError) as exc:
        return {"ok": False, "error": f"chromaprint ctypes probe failed: {exc}"}

    # Fall through to fpcalc for actual fingerprint when pyacoustid absent.
    fpcalc_result = _fingerprint_fpcalc(path, duration=duration)
    if fpcalc_result.get("ok"):
        fpcalc_result["backend"] = f"fpcalc+chromaprint-{version_str}"
    return fpcalc_result


def find_fpcalc() -> Path | None:
    env = os.environ.get("FPCALC_PATH", "").strip()
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return candidate
    found = shutil.which("fpcalc")
    return Path(found) if found else None


def _fingerprint_fpcalc(path: Path, *, duration: int = 120) -> dict[str, Any]:
    fpcalc = find_fpcalc()
    if fpcalc is None:
        return {"ok": False, "error": "fpcalc not found — install Chromaprint or set FPCALC_PATH"}

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
        "backend": "fpcalc",
    }


def fingerprint_file(path: Path, *, duration: int = 120, prefer_native: bool = True) -> dict[str, Any]:
    """Return Chromaprint fingerprint for an audio file, or error metadata."""
    if path.suffix.lower() not in AUDIO_EXTS:
        return {"ok": False, "error": f"unsupported extension: {path.suffix}"}

    if prefer_native and (os.environ.get("CHROMAPRINT_LIB") or _load_chromaprint()):
        native = _fingerprint_native(path, duration=duration)
        if native.get("ok"):
            return native

    return _fingerprint_fpcalc(path, duration=duration)
