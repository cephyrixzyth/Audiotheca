"""Per-run reference dedupe configuration (Phase G)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from api.paths import report_dir

CONFIG_DIR = report_dir() / "decisions"
VALID_MODES = frozenset({"keep_reference"})


def _config_path(stamp: str) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR / f"reference_config_{stamp}.json"


def load_reference_config(stamp: str) -> dict[str, object] | None:
    path = _config_path(stamp)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return data


def save_reference_config(
    stamp: str,
    *,
    reference_roots: list[str],
    reference_mode: str = "keep_reference",
) -> dict[str, object]:
    mode = str(reference_mode or "").strip()
    if mode not in VALID_MODES:
        raise ValueError(f"reference_mode must be one of: {', '.join(sorted(VALID_MODES))}")
    roots = [str(root).strip() for root in reference_roots if str(root).strip()]
    if not roots:
        raise ValueError("reference_roots is required")

    payload = {
        "stamp": stamp,
        "reference_roots": roots,
        "reference_mode": mode,
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    path = _config_path(stamp)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def reference_roots_for_run(stamp: str) -> list[str]:
    config = load_reference_config(stamp)
    if not config:
        return []
    roots = config.get("reference_roots") or []
    return [str(root).strip() for root in roots if str(root).strip()]
