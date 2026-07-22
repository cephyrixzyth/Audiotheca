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
    if parts[0] == "//":
        if len(parts) == 1:
            return Path("//")
        host = parts[1]
        rest = parts[2:]
        if rest:
            return Path("//" + host + "/" + "/".join(rest))
        return Path("//" + host)
    return Path("/".join(parts))


def _is_logical_root_marker(parts: list[str]) -> bool:
    if not parts:
        return True
    if parts == [""]:
        return True
    if len(parts) == 1 and len(parts[0]) == 2 and parts[0][1] == ":":
        return True
    if parts[0] == "//" and len(parts) <= 2:
        return True
    return False


def collapse_logical_parts(parts: list[str]) -> list[str]:
    """Collapse ``.`` / ``..`` without following symlinks.

    Raises ValueError when ``..`` would escape above a drive/UNC/Unix root.
    """
    if not parts:
        return []
    out: list[str] = []
    index = 0
    if parts[0] == "":
        out.append("")
        index = 1
    elif len(parts[0]) == 2 and parts[0][1] == ":":
        out.append(parts[0])
        index = 1
    elif parts[0] == "//":
        out.append("//")
        index = 1
        if len(parts) > 1:
            out.append(parts[1])
            index = 2

    for part in parts[index:]:
        if part in {"", "."}:
            continue
        if part == "..":
            if _is_logical_root_marker(out):
                raise ValueError("path escapes via ..")
            if out and out[-1] == "..":
                out.append("..")
                continue
            out.pop()
            continue
        out.append(part)
    return out


def collapse_logical_path(path: Path | str) -> Path:
    """Return path with ``.`` / ``..`` collapsed; raises ValueError on root escape."""
    return logical_path_from_parts(collapse_logical_parts(logical_path_parts(path)))


def normalize_logical_path(path: Path | str) -> str:
    parts = collapse_logical_parts(logical_path_parts(path))
    return "/".join(part.lower() for part in parts)


def is_logical_path_under(child: Path | str, parent: Path | str) -> bool:
    try:
        child_parts = collapse_logical_parts(logical_path_parts(child))
        parent_parts = collapse_logical_parts(logical_path_parts(parent))
    except ValueError:
        return False
    if len(child_parts) < len(parent_parts):
        return False
    return child_parts[: len(parent_parts)] == parent_parts
