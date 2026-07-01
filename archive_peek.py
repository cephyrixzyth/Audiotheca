"""
Archive introspection: list contents without extracting, infer scene-hash identities,
and diagnose multipart RAR sets. Used by main.py and peek_archives.py.
"""

from __future__ import annotations

import csv
import re
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path

ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".iso", ".tar", ".gz", ".001"}
MAX_LIST_ENTRIES = 40
MAX_PEEK_BYTES = 500 * 1024 * 1024 * 1024
MULTIPART_RE = re.compile(r"(?i)^(.+?)\.part(\d+)\.(rar|zip|7z)$")
SEVEN_Z_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+.+?\s+\d+\s+\d+\s+(.+)$")
LISTING_ARTIFACT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s+(?:\d{2}:\d{2}:\d{2}|\d{6})\s+"
    r"[D\.\-A\.\s]+.*?\s{2,}(.+)$"
)
FOLDER_NAME_EXTENSIONS = (".zip", ".rar", ".7z", ".exe", ".msi", ".app", ".iso")
SCENE_RENAME_SKIP_SUBSTRINGS = (
    "requirements for installations",
    "daw-setup-guide",
    "setup guide",
)
SCENE_JUNK_DIRS = {
    "r2r", "btcr", "mocha", "crack", "keygen", "patch", "team", "wifi",
    "__macosx", "discover", "nebula",
}


def find_7z() -> Path | None:
    import shutil
    import sys

    from audiotheca.tools_paths import bundled_7z_candidates

    for candidate in bundled_7z_candidates():
        if candidate.is_file():
            return candidate

    candidates: list[Path] = []
    if sys.platform == "win32":
        candidates.extend([
            Path(r"C:\Program Files\7-Zip\7z.exe"),
            Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
        ])
    elif sys.platform == "darwin":
        candidates.extend([
            Path("/opt/homebrew/bin/7z"),
            Path("/usr/local/bin/7z"),
        ])
    else:
        candidates.extend([
            Path("/usr/bin/7z"),
            Path("/usr/bin/7za"),
            Path("/usr/local/bin/7z"),
        ])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    for name in ("7z", "7za", "7zr"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def strip_listing_artifact(name: str) -> str:
    """Remove 7-Zip -l timestamp/attribute prefixes that leak into inferred names."""
    text = name.strip()
    if not text:
        return text
    match = LISTING_ARTIFACT_RE.match(text)
    if match:
        return match.group(1).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}\s", text):
        parts = re.split(r"\s{2,}", text)
        if len(parts) >= 2:
            candidate = parts[-1].strip()
            if candidate and not re.match(r"^\d+$", candidate):
                return candidate
    return text


def scene_rename_blocked(proposed_name: str) -> str | None:
    """Return skip reason when a proposed scene folder name should not be applied."""
    lower = proposed_name.lower()
    for fragment in SCENE_RENAME_SKIP_SUBSTRINGS:
        if fragment in lower:
            return f"weak name ({fragment})"
    return None


def normalize_inferred_product(name: str) -> str:
    """Clean inferred titles before using them as on-disk folder names."""
    cleaned = strip_listing_artifact(name).strip()
    lowered = cleaned.lower()
    for ext in FOLDER_NAME_EXTENSIONS:
        if lowered.endswith(ext):
            cleaned = cleaned[: -len(ext)].strip()
            lowered = cleaned.lower()
    return cleaned[:120]


def parse_7z_list_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("-"):
        return None
    match = SEVEN_Z_LINE_RE.match(stripped)
    if match:
        return match.group(1).replace("\\", "/")
    if "/" in stripped or "." in stripped:
        return stripped.replace("\\", "/")
    return None


def peek_zip(archive: Path, limit: int) -> tuple[list[str], str | None]:
    try:
        with zipfile.ZipFile(archive, "r") as handle:
            names = sorted(handle.namelist(), key=lambda n: (n.count("/"), n.lower()))
            return names[:limit], None
    except (OSError, zipfile.BadZipFile) as exc:
        return [], str(exc)


def peek_7z(archive: Path, seven_zip: Path, limit: int) -> tuple[list[str], str | None]:
    try:
        proc = subprocess.run(
            [str(seven_zip), "l", "-ba", str(archive)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            err = (proc.stderr or proc.stdout or "").strip()
            return [], err.splitlines()[-1][:200] if err else f"7z exit {proc.returncode}"

        paths: list[str] = []
        for line in proc.stdout.splitlines():
            parsed = parse_7z_list_line(line)
            if parsed:
                paths.append(parsed)
        paths.sort(key=lambda n: (n.count("/"), n.lower()))
        return paths[:limit], None
    except subprocess.TimeoutExpired:
        return [], "7z list timed out (180s)"
    except OSError as exc:
        return [], str(exc)


def peek_archive(archive: Path, seven_zip: Path | None, limit: int = MAX_LIST_ENTRIES) -> tuple[list[str], str | None]:
    if not archive.is_file():
        return [], "archive file missing"
    try:
        if archive.stat().st_size > MAX_PEEK_BYTES:
            return [], f"archive too large to list (>{MAX_PEEK_BYTES // (1024**3)} GB)"
    except OSError as exc:
        return [], str(exc)

    ext = archive.suffix.lower()
    if ext == ".zip":
        return peek_zip(archive, limit)
    if ext in {".rar", ".7z", ".tar", ".gz", ".001", ".iso"}:
        if seven_zip is None:
            return [], "needs 7-Zip (7z.exe) for non-zip archives"
        return peek_7z(archive, seven_zip, limit)
    return [], f"unsupported extension {ext}"


def multipart_key(archive_name: str) -> tuple[str, int] | None:
    match = MULTIPART_RE.match(archive_name)
    if not match:
        return None
    return match.group(1).lower(), int(match.group(2))


def archives_to_peek(archive_names: list[str]) -> list[tuple[str, str]]:
    chosen: dict[str, tuple[str, int]] = {}
    singles: list[str] = []
    for name in archive_names:
        part = multipart_key(name)
        if part is None:
            singles.append(name)
            continue
        base, idx = part
        if base not in chosen or idx < chosen[base][1]:
            chosen[base] = (name, idx)

    result = [(name, "") for name in singles]
    result.extend((name, "") for name, _idx in chosen.values())
    peeked = {name for name, _ in result}
    skipped = [(name, "MULTIPART_SECONDARY") for name in archive_names if name not in peeked]
    return result + skipped


def summarize_entries(names: list[str]) -> dict:
    if not names:
        return {"top_dirs": "", "extensions": "", "entry_count": 0}

    dirs: set[str] = set()
    exts: dict[str, int] = defaultdict(int)
    for name in names:
        parts = name.replace("\\", "/").split("/")
        if len(parts) > 1 and parts[0]:
            top = strip_listing_artifact(parts[0])
            if top:
                dirs.add(top)
        leaf = parts[-1]
        if "." in leaf:
            ext = leaf.rsplit(".", 1)[-1].lower()
            if ext:
                exts[ext] += 1

    top_ext = ", ".join(f"{k}({v})" for k, v in sorted(exts.items(), key=lambda x: -x[1])[:8])
    return {
        "top_dirs": ", ".join(sorted(dirs)[:12]),
        "extensions": top_ext,
        "entry_count": len(names),
    }


def classify_peek(folder_name: str, sample_names: list[str], error: str | None) -> str:
    if error:
        if "missing" in error.lower():
            return "ARCHIVE_MISSING"
        if "needs 7-Zip" in error:
            return "NEEDS_7ZIP"
        if "too large" in error:
            return "TOO_LARGE"
        return "LIST_FAILED"

    folder = folder_name.lower()
    joined = " ".join(sample_names).lower()
    if folder and folder in joined:
        return "MATCHES_EXTRACTED_FOLDER"
    if re.search(r"(?i)\.(exe|msi|dll|vst3|aaxplugin|nki|iso)\b", joined):
        return "LOOKS_LIKE_PRODUCT"
    if re.search(r"(?i)(keygen|patch|crack|nfo|\.diz|\.sfv)", joined):
        return "SCENE_CRACK_JUNK"
    if sample_names:
        return "UNKNOWN_CONTENT"
    return "EMPTY_OR_UNREADABLE"


def infer_product_identity(sample_names: list[str], top_level_dirs: str = "") -> str | None:
    """Best-effort product title from archive listing (for scene-hash rename)."""
    candidates: list[str] = []

    for name in sample_names:
        parts = name.replace("\\", "/").split("/")
        if not parts or not parts[0]:
            continue
        top = strip_listing_artifact(parts[0].strip())
        if not top or top.lower() in SCENE_JUNK_DIRS:
            continue
        if re.match(r"(?i)^r2r\d+$", top):
            continue
        if re.match(r"^\d{4}-\d{2}-\d{2}\s", top):
            continue
        leaf = strip_listing_artifact(parts[-1].strip())
        if re.search(r"(?i)setup .+\.(exe|msi)$", leaf):
            return normalize_inferred_product(
                re.sub(r"(?i)^setup\s+", "", leaf).rsplit(".", 1)[0].strip()
            )
        if len(top) >= 6 and not re.match(r"^\d{5,}$", top):
            candidates.append(top)

    if top_level_dirs:
        for token in top_level_dirs.split(", "):
            token = strip_listing_artifact(token.strip())
            if (
                len(token) >= 6
                and token.lower() not in SCENE_JUNK_DIRS
                and not re.match(r"^\d{4}-\d{2}-\d{2}\s", token)
            ):
                candidates.append(token)

    if not candidates:
        return None

    candidates.sort(key=lambda value: (-len(value), value.lower()))
    return normalize_inferred_product(candidates[0])


def diagnose_multipart_folder(folder: Path, seven_zip: Path | None) -> dict:
    """Detect missing part01, sequence gaps, or corrupt first part (e.g. 287901)."""
    part_files: dict[str, list[tuple[int, Path]]] = defaultdict(list)
    for entry in folder.iterdir():
        if not entry.is_file():
            continue
        part = multipart_key(entry.name)
        if part:
            base, idx = part
            part_files[base].append((idx, entry))

    if not part_files:
        return {
            "folder_path": str(folder),
            "scene_id": folder.name,
            "multipart_base": "",
            "part_count": 0,
            "part_min": "",
            "part_max": "",
            "missing_parts": "",
            "part01_path": "",
            "part01_openable": "",
            "diagnosis": "NO_MULTIPART_ARCHIVES",
            "detail": "no .partN.rar files at folder root",
        }

    base, parts = max(part_files.items(), key=lambda row: len(row[1]))
    parts.sort(key=lambda row: row[0])
    indices = [idx for idx, _path in parts]
    part_min, part_max = min(indices), max(indices)
    missing = [str(n) for n in range(part_min, part_max + 1) if n not in indices]
    part01 = next((path for idx, path in parts if idx == 1), None)
    if part01 is None:
        part01 = next((path for idx, path in parts if idx == min(indices)), None)

    openable = ""
    diagnosis = "OK"
    detail = ""
    if part_min > 1:
        diagnosis = "MISSING_PART01"
        detail = f"lowest part is part{part_min:02d}, part01 not found"
    elif missing:
        diagnosis = "GAP_IN_SEQUENCE"
        detail = f"missing parts: {', '.join(missing[:12])}"
    elif part01 and seven_zip:
        names, error = peek_archive(part01, seven_zip, limit=5)
        openable = "yes" if names and not error else "no"
        if error or not names:
            diagnosis = "CORRUPT_OR_UNREADABLE_PART01"
            detail = error or "part01 listed empty"
    elif part01 and not seven_zip:
        diagnosis = "NEEDS_7ZIP"
        detail = "install 7-Zip to test part01"

    return {
        "folder_path": str(folder),
        "scene_id": folder.name,
        "multipart_base": base,
        "part_count": len(parts),
        "part_min": part_min,
        "part_max": part_max,
        "missing_parts": ", ".join(missing[:20]),
        "part01_path": str(part01) if part01 else "",
        "part01_openable": openable,
        "diagnosis": diagnosis,
        "detail": detail,
    }


def peek_sibling_groups(
    groups: list[dict],
    seven_zip: Path | None,
    *,
    progress_callback=None,
) -> list[dict]:
    rows: list[dict] = []
    for index, group in enumerate(groups):
        item_path = group["item_path"]
        for archive_name, skip_reason in archives_to_peek(group["archives"]):
            arch_path = group.get("archive_path")
            if arch_path is None:
                parent = group.get("parent", ".")
                base = item_path if parent in {".", ""} else item_path / parent.replace("\\", "/")
                arch_path = base / archive_name
            else:
                arch_path = Path(arch_path)

            if skip_reason:
                rows.append(_peek_row(group, archive_name, arch_path, skip_reason, [], "MULTIPART_SECONDARY"))
                continue

            names, error = peek_archive(arch_path, seven_zip)
            summary = summarize_entries(names)
            verdict = classify_peek(group.get("folder_name", ""), names, error)
            rows.append(
                _peek_row(
                    group,
                    archive_name,
                    arch_path,
                    error or "",
                    names,
                    verdict,
                    summary,
                )
            )
        if progress_callback:
            progress_callback(index + 1, group.get("item_name", ""))
    return rows


def _peek_row(
    group: dict,
    archive_name: str,
    arch_path: Path,
    error: str,
    names: list[str],
    verdict: str,
    summary: dict | None = None,
) -> dict:
    summary = summary or summarize_entries(names)
    size_mb = ""
    if arch_path.is_file():
        try:
            size_mb = round(arch_path.stat().st_size / (1024 * 1024), 1)
        except OSError:
            pass
    return {
        "section": group.get("section", ""),
        "item_name": group.get("item_name", ""),
        "item_path": str(group.get("item_path", "")),
        "archive_name": archive_name,
        "archive_path": str(arch_path),
        "extracted_folder": group.get("folder_name", ""),
        "name_similarity": group.get("similarity", ""),
        "archive_exists": arch_path.is_file(),
        "archive_size_mb": size_mb,
        "list_error": error,
        "verdict": verdict,
        "entry_count_sampled": summary["entry_count"],
        "top_level_dirs": summary["top_dirs"],
        "extensions": summary["extensions"],
        "sample_entries": " | ".join(names[:8]),
        "inferred_product": infer_product_identity(names, summary["top_dirs"]) or "",
    }


def sibling_groups_from_coexistence(coexistence_rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str, str], dict] = {}
    for row in coexistence_rows:
        if row.get("issue_type") != "ARCHIVE_EXTRACTED_SIBLING":
            continue
        key = (row.get("item_path", ""), row.get("parent", "."), row.get("folder_name", ""))
        entry = groups.setdefault(
            key,
            {
                "section": row.get("source_bin", ""),
                "item_name": row.get("item_name", ""),
                "item_path": Path(row["item_path"]),
                "parent": row.get("parent", "."),
                "folder_name": row.get("folder_name", ""),
                "archives": [],
                "similarity": row.get("similarity", ""),
            },
        )
        arch = row.get("archive_name", "")
        if arch and arch not in entry["archives"]:
            entry["archives"].append(arch)
    return list(groups.values())


def peek_scene_folders(
    scene_items: list[dict],
    seven_zip: Path | None,
    *,
    min_size_mb: float = 1000,
    limit: int | None = None,
    progress_callback=None,
) -> tuple[list[dict], list[dict]]:
    """Peek scene-hash folders and run multipart diagnostics. Returns (peek_rows, diagnostic_rows)."""
    candidates = sorted(
        [item for item in scene_items if float(item.get("size_mb", 0) or 0) >= min_size_mb],
        key=lambda row: -float(row.get("size_mb", 0) or 0),
    )
    if limit:
        candidates = candidates[:limit]

    peek_rows: list[dict] = []
    diagnostic_rows: list[dict] = []

    for index, item in enumerate(candidates):
        folder = Path(item["path"]) if "path" in item else Path(item["current_path"])
        if not folder.is_dir():
            continue

        diagnostic_rows.append(diagnose_multipart_folder(folder, seven_zip))

        archives = sorted(
            [
                entry
                for entry in folder.iterdir()
                if entry.is_file() and entry.suffix.lower() in ARCHIVE_EXTS
            ],
            key=lambda entry: multipart_key(entry.name) or (entry.stem.lower(), 0),
        )
        if not archives:
            peek_rows.append(
                {
                    "scene_id": item.get("original_name", folder.name),
                    "folder_path": str(folder),
                    "size_mb": item.get("size_mb", ""),
                    "archive_name": "",
                    "archive_path": "",
                    "verdict": "NO_TOP_LEVEL_ARCHIVE",
                    "inferred_product": "",
                    "sample_entries": "",
                    "list_error": "no archive at folder root",
                }
            )
        else:
            to_list = archives_to_peek([arch.name for arch in archives])
            listed = 0
            for arch in archives:
                skip = next((reason for name, reason in to_list if name == arch.name and reason), "")
                if skip == "MULTIPART_SECONDARY":
                    continue
                if listed >= 1:
                    break
                names, error = peek_archive(arch, seven_zip)
                summary = summarize_entries(names)
                verdict = classify_peek(folder.name, names, error)
                inferred = infer_product_identity(names, summary["top_dirs"]) or ""
                peek_rows.append(
                    {
                        "scene_id": item.get("original_name", folder.name),
                        "folder_path": str(folder),
                        "size_mb": item.get("size_mb", ""),
                        "archive_name": arch.name,
                        "archive_path": str(arch),
                        "verdict": verdict,
                        "inferred_product": inferred,
                        "sample_entries": " | ".join(names[:8]),
                        "list_error": error or "",
                    }
                )
                listed += 1

        if progress_callback:
            progress_callback(index + 1, item.get("original_name", folder.name))

    return peek_rows, diagnostic_rows


def write_peek_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
