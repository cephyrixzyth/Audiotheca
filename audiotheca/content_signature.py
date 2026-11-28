"""Content signatures for duplicate identification.

Name matching alone misses renamed copies ("Silent Thunder Drums" vs
"STD_Collection_FINAL") and cannot tell a complete pack from a half-copied
one with the same name. This module builds a cheap manifest signature from
data the scan walk already has (file names and sizes from the directory
listing — no extra reads), so folders can be compared by what they contain:

* ``tree_sig``  — exact layout: sorted (relative path, size) pairs.
* ``loose_sig`` — layout-independent: sorted (file name, size) pairs. Survives
  an extra wrapper folder or a reorganised subfolder tree.
* ``sketch``    — bottom-k MinHash of the (file name, size) entries, used to
  estimate overlap (Jaccard / containment) between packs that are *nearly*
  the same: partial copies, packs with a bonus folder, re-releases.

The same manifest can be built from an archive listing (zip natively, other
formats through 7-Zip) so an archive can be verified against an extracted
folder instead of being matched on name alone.
"""

from __future__ import annotations

import hashlib
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable

SKETCH_K = 128
MANIFEST_SCHEMA = 1

# Files that differ between otherwise identical copies and say nothing about
# the payload: OS litter and scene release metadata.
_JUNK_NAMES = frozenset({".ds_store", "thumbs.db", "desktop.ini", "icon\r", ".localized"})
_JUNK_EXTS = frozenset({"nfo", "sfv", "diz", "url", "md5", "sha1", "par2"})

# Archive listing guards — listing is metadata only, but very large or slow
# archives should never stall the duplicate phase.
ARCHIVE_LIST_MAX_BYTES = 20 * 1024**3
ARCHIVE_LIST_MAX_ENTRIES = 200_000
ARCHIVE_LIST_TIMEOUT_S = 120


def is_junk_file(name: str) -> bool:
    lowered = name.lower()
    if lowered in _JUNK_NAMES or lowered.startswith("._"):
        return True
    ext = lowered.rsplit(".", 1)[-1] if "." in lowered else ""
    return ext in _JUNK_EXTS


def _entry_hash(name: str, size: int) -> int:
    digest = hashlib.blake2b(f"{name}\0{size}".encode("utf-8", "surrogatepass"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


class ManifestBuilder:
    """Accumulates (relative path, size) pairs during a walk."""

    __slots__ = ("_tree", "_loose", "_hashes", "total_bytes", "truncated")

    def __init__(self) -> None:
        self._tree: list[str] = []
        self._loose: list[str] = []
        self._hashes: set[int] = set()
        self.total_bytes = 0
        self.truncated = False

    def add(self, rel_path: str, size: int) -> None:
        rel = str(rel_path).replace("\\", "/").strip("/")
        name = PurePosixPath(rel).name
        if not name or size <= 0 or is_junk_file(name):
            return
        rel_lower = rel.lower()
        name_lower = name.lower()
        self._tree.append(f"{rel_lower}\0{size}")
        self._loose.append(f"{name_lower}\0{size}")
        self._hashes.add(_entry_hash(name_lower, size))
        self.total_bytes += size

    def finalize(self) -> dict:
        if not self._tree:
            return {}
        tree = hashlib.sha1("\n".join(sorted(self._tree)).encode("utf-8", "surrogatepass")).hexdigest()
        loose = hashlib.sha1("\n".join(sorted(self._loose)).encode("utf-8", "surrogatepass")).hexdigest()
        return {
            "schema": MANIFEST_SCHEMA,
            "file_count": len(self._tree),
            "total_bytes": self.total_bytes,
            "tree_sig": tree,
            "loose_sig": loose,
            "sketch": sorted(self._hashes)[:SKETCH_K],
            "truncated": self.truncated,
        }


def manifest_from_entries(entries: Iterable[tuple[str, int]]) -> dict:
    builder = ManifestBuilder()
    for rel, size in entries:
        builder.add(rel, int(size or 0))
    return builder.finalize()


def manifest_for_folder(root: Path, *, max_files: int = ARCHIVE_LIST_MAX_ENTRIES) -> dict:
    """Walk ``root`` and build a manifest (used when the scan cache lacks one)."""
    import os

    builder = ManifestBuilder()
    count = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            rel = str(Path(entry.path).relative_to(root))
                            builder.add(rel, entry.stat(follow_symlinks=False).st_size)
                            count += 1
                            if count >= max_files:
                                builder.truncated = True
                                return builder.finalize()
                    except OSError:
                        continue
        except OSError:
            continue
    return builder.finalize()


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def sketch_jaccard(left: list[int], right: list[int], k: int = SKETCH_K) -> float:
    """Bottom-k Jaccard estimate. Exact when both sets have fewer than k entries."""
    if not left or not right:
        return 0.0
    a, b = set(left), set(right)
    union_bottom = sorted(a | b)[:k]
    if not union_bottom:
        return 0.0
    shared = sum(1 for value in union_bottom if value in a and value in b)
    return shared / len(union_bottom)


def compare_manifests(left: dict, right: dict) -> dict:
    """Return overlap metrics between two manifests.

    ``containment`` is the estimated share of the *smaller* manifest's files
    that also exist in the larger one — 1.0 means one copy is a subset.
    """
    if not left or not right:
        return {"relation": "UNKNOWN", "jaccard": 0.0, "containment": 0.0}
    if left.get("tree_sig") and left.get("tree_sig") == right.get("tree_sig"):
        return {"relation": "IDENTICAL", "jaccard": 1.0, "containment": 1.0}
    if left.get("loose_sig") and left.get("loose_sig") == right.get("loose_sig"):
        return {"relation": "SAME_FILES_MOVED", "jaccard": 1.0, "containment": 1.0}

    jaccard = sketch_jaccard(left.get("sketch") or [], right.get("sketch") or [])
    n_left = int(left.get("file_count") or 0)
    n_right = int(right.get("file_count") or 0)
    small = min(n_left, n_right)
    if small <= 0 or jaccard <= 0:
        containment = 0.0
    else:
        intersection = jaccard * (n_left + n_right) / (1.0 + jaccard)
        containment = min(1.0, intersection / small)

    if jaccard >= 0.9:
        relation = "NEAR_IDENTICAL"
    elif containment >= 0.95 and n_left != n_right:
        relation = "SUBSET"
    elif jaccard >= 0.5:
        relation = "OVERLAP"
    elif jaccard > 0:
        relation = "PARTIAL_OVERLAP"
    else:
        relation = "DIFFERENT"
    return {"relation": relation, "jaccard": round(jaccard, 3), "containment": round(containment, 3)}


def describe_relation(cmp: dict, left_count: int, right_count: int) -> str:
    relation = cmp.get("relation", "UNKNOWN")
    if relation == "IDENTICAL":
        return f"same {left_count} files, same layout"
    if relation == "SAME_FILES_MOVED":
        return f"same {left_count} files, different folder layout"
    if relation == "UNKNOWN":
        return "no file manifest to compare"
    pct = round(100 * float(cmp.get("jaccard") or 0))
    contain = round(100 * float(cmp.get("containment") or 0))
    base = f"{left_count} vs {right_count} files, ~{pct}% shared"
    if relation == "SUBSET":
        return f"{base} (smaller copy is ~{contain}% contained in the larger — partial copy)"
    return base


# ---------------------------------------------------------------------------
# Archive listings
# ---------------------------------------------------------------------------


def _strip_common_root(entries: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Drop a single shared top folder ("Pack/…") so archive paths line up with
    the extracted folder, which is usually that top folder itself."""
    if not entries:
        return entries
    firsts = {rel.replace("\\", "/").strip("/").split("/", 1)[0] for rel, _ in entries}
    if len(firsts) != 1:
        return entries
    if not all("/" in rel.replace("\\", "/").strip("/") for rel, _ in entries):
        return entries
    return [(rel.replace("\\", "/").strip("/").split("/", 1)[1], size) for rel, size in entries]


def _list_zip(archive: Path) -> list[tuple[str, int]] | None:
    try:
        with zipfile.ZipFile(archive, "r") as handle:
            out: list[tuple[str, int]] = []
            for info in handle.infolist():
                if info.is_dir():
                    continue
                out.append((info.filename, int(info.file_size)))
                if len(out) >= ARCHIVE_LIST_MAX_ENTRIES:
                    break
            return out
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError):
        return None


def parse_7z_slt(text: str) -> list[tuple[str, int]]:
    """Parse ``7z l -slt`` technical listing into (path, size) pairs."""
    out: list[tuple[str, int]] = []
    block: dict[str, str] = {}

    def flush() -> None:
        path = block.get("Path")
        if path and block.get("Folder", "-") != "+" and "D" not in block.get("Attributes", "")[:1]:
            try:
                out.append((path, int(block.get("Size") or 0)))
            except ValueError:
                pass

    for line in text.splitlines():
        if not line.strip():
            if block:
                flush()
                block = {}
            continue
        if " = " in line:
            key, _, value = line.partition(" = ")
            block[key.strip()] = value.strip()
    if block:
        flush()
    return out


def _list_7z(archive: Path, seven_zip: Path) -> list[tuple[str, int]] | None:
    try:
        proc = subprocess.run(
            [str(seven_zip), "l", "-slt", "-ba", str(archive)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=ARCHIVE_LIST_TIMEOUT_S,
            check=False,
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return parse_7z_slt(proc.stdout)[:ARCHIVE_LIST_MAX_ENTRIES]


def manifest_for_archive(archive: Path, seven_zip: Path | None = None) -> dict:
    """Manifest of an archive's contents, or {} when it cannot be listed."""
    try:
        if not archive.is_file() or archive.stat().st_size > ARCHIVE_LIST_MAX_BYTES:
            return {}
    except OSError:
        return {}
    ext = archive.suffix.lower()
    entries: list[tuple[str, int]] | None
    if ext == ".zip":
        entries = _list_zip(archive)
    elif seven_zip is not None:
        entries = _list_7z(archive, seven_zip)
    else:
        entries = None
    if not entries:
        return {}
    return manifest_from_entries(_strip_common_root(entries))
