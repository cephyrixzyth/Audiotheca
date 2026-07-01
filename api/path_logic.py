"""Cross-platform path parsing for Windows library paths on non-Windows hosts."""

from __future__ import annotations

from pathlib import Path


def logical_path_parts(path: Path | str) -> list[str]:
    """Split a path into components regardless of host OS separator rules."""
    text = str(path).replace("\\", "/").strip()
    if not text:
        return []
    if text.startswith("//"):
        remainder = text[2:]
        if "/" in remainder:
            host, tail = remainder.split("/", 1)
            return ["//", host, *logical_path_parts(tail)]
        return ["//", remainder]
    parts = [part for part in text.split("/") if part]
    if text.startswith("/"):
        return ["", *parts]
    return parts


def logical_path_from_parts(parts: list[str]) -> Path:
    if not parts:
        return Path(".")
    if parts[0] == "":
        return Path("/" + "/".join(parts[1:]))
    if len(parts[0]) == 2 and parts[0][1] == ":":
        drive = parts[0]
        rest = parts[1:]
        if rest:
            return Path(f"{drive}\\" + "\\".join(rest))
        return Path(f"{drive}\\")
    return Path("/".join(parts))


def normalize_logical_path(path: Path | str) -> str:
    parts = logical_path_parts(path)
    return "/".join(part.lower() for part in parts)


def is_logical_path_under(child: Path | str, parent: Path | str) -> bool:
    child_parts = logical_path_parts(child)
    parent_parts = logical_path_parts(parent)
    if len(child_parts) < len(parent_parts):
        return False
    return child_parts[: len(parent_parts)] == parent_parts
