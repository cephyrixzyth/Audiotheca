"""XFER-BNDL: self-contained deployment bundle export."""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def export_bundle(
    output: str | Path,
    *,
    manifest: dict[str, Any] | None = None,
    files: list[str] | None = None,
) -> dict[str, Any]:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest or {"kind": "audiotheca_bundle"}, indent=2))
        added += 1
        for path in files or []:
            src = Path(path)
            if src.is_file():
                zf.write(src, arcname=src.name)
                added += 1
    return {"output": str(target), "entries": added, "ok": True}


def export_workspace_bundle(
    output: str | Path,
    *,
    home: str | Path | None = None,
    include_ledger: bool = True,
    include_audit: bool = True,
) -> dict[str, Any]:
    """Pack manifest, ledger, and audit snapshots from AUDIOTHECA_HOME."""
    root = Path(home or os.environ.get("AUDIOTHECA_HOME", Path.home() / ".audiotheca"))
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "kind": "audiotheca_workspace_bundle",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "home": str(root),
    }
    included: list[str] = []

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        included.append("manifest.json")

        if include_ledger:
            ledger = root / "transaction_ledger.jsonl"
            if ledger.is_file():
                zf.write(ledger, arcname="transaction_ledger.jsonl")
                included.append("transaction_ledger.jsonl")

        if include_audit:
            audit = root / "audit.log"
            if audit.is_file():
                zf.write(audit, arcname="audit.log")
                included.append("audit.log")

        env_manifest = root / "environment_manifest.json"
        if env_manifest.is_file():
            zf.write(env_manifest, arcname="environment_manifest.json")
            included.append("environment_manifest.json")

        layout_dir = root / "layouts"
        if layout_dir.is_dir():
            for layout in layout_dir.glob("*.json"):
                zf.write(layout, arcname=f"layouts/{layout.name}")
                included.append(f"layouts/{layout.name}")

    return {
        "output": str(target),
        "entries": len(included),
        "included": included,
        "ok": True,
    }
