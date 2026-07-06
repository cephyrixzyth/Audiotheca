"""PATH-RLOC: cross-platform project path translation."""

from __future__ import annotations

from typing import Any


def translate_path(path: str, *, target_os: str = "mac", custom_map: dict[str, str] | None = None) -> dict[str, Any]:
    text = path.replace("\\", "/")
    translated = text

    if custom_map:
        for src, dst in sorted(custom_map.items(), key=lambda item: len(item[0]), reverse=True):
            norm_src = src.replace("\\", "/")
            if translated.startswith(norm_src):
                translated = dst.replace("\\", "/") + translated[len(norm_src) :]
                break

    if target_os == "mac" and translated == text:
        translated = text.replace("C:/Users/", "/Users/").replace("D:/", "/Volumes/")
    elif target_os == "win" and translated == text:
        translated = text.replace("/Users/", "C:/Users/").replace("/Volumes/", "D:/")

    return {"source": path, "target_os": target_os, "translated": translated}


def build_map(pairs: list[dict[str, str]]) -> dict[str, str]:
    return {p["win"]: p["mac"] for p in pairs if "win" in p and "mac" in p}


def translate_batch(paths: list[str], *, target_os: str = "mac", custom_map: dict[str, str] | None = None) -> dict[str, Any]:
    rows = [translate_path(p, target_os=target_os, custom_map=custom_map) for p in paths]
    return {"target_os": target_os, "count": len(rows), "rows": rows}
