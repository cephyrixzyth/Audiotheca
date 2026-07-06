"""V-MATX: plugin version matrix from installation registry."""

from __future__ import annotations

from typing import Any

from installation_registry import list_installs


def build_version_matrix(*, formats: tuple[str, ...] = ("vst3", "aax", "au", "clap")) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for record in list_installs():
        path_lower = str(record.get("install_path", "")).lower()
        fmt = next((f for f in formats if f in path_lower), "unknown")
        rows.append(
            {
                "product_key": record.get("product_key", ""),
                "display_name": record.get("display_name", ""),
                "format": fmt,
                "local_version": record.get("local_version", ""),
                "manifest_version": record.get("manifest_version", ""),
                "update_status": record.get("update_status", "unknown"),
            }
        )
    return {"formats": list(formats), "rows": rows, "count": len(rows)}
