"""Read current run evidence and identify every member of an approved archive move."""

import csv
import hashlib
import os
import stat
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

from api.paths import report_dir
from archive_peek import find_7z, multipart_key
from audiotheca.file_integrity import content_identity


def expand_multipart_set(archive: Path) -> list[Path]:
    part = multipart_key(archive.name)
    if part is None:
        return [archive]
    members = [(multipart_key(p.name), p) for p in archive.parent.iterdir() if p.suffix.lower() == archive.suffix.lower()]
    numbered = sorted((key[1], p) for key, p in members if key and key[0] == part[0])
    if [n for n, _ in numbered] != list(range(1, len(numbered) + 1)):
        raise ValueError("Incomplete or ambiguous multipart archive")
    return [p for _, p in numbered]


def _member_parts(name: str) -> tuple[str, ...]:
    member = PurePosixPath(name.replace("\\", "/"))
    if member.is_absolute() or ".." in member.parts or not member.parts or ":" in member.parts[0]:
        raise ValueError(f"Unsafe archive member: {name}")
    return member.parts


def _verify_folder(archive: Path, folder: Path, part_count: int) -> None:
    if not folder.is_dir() or folder.is_symlink() or folder.resolve().parent != archive.resolve().parent:
        raise ValueError("Verified extracted sibling is required")
    records = []
    if archive.suffix.lower() == ".zip" and multipart_key(archive.name) is None:
        with zipfile.ZipFile(archive) as zipped:
            for info in zipped.infolist():
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("ZIP contains a link")
                digest = None
                if not info.is_dir():
                    with zipped.open(info) as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                records.append((_member_parts(info.filename), info.file_size, digest))
    else:
        tool = find_7z()
        if not tool:
            raise ValueError("7-Zip is required to verify this archive")
        if part_count > 1:
            inventory = subprocess.run([str(tool), "l", "-slt", "--", str(archive)],
                                       capture_output=True, text=True, timeout=180, check=True, stdin=subprocess.DEVNULL)
            header = inventory.stdout.split("----------", 1)[0]
            if f"Volumes = {part_count}" not in header.splitlines():
                raise ValueError("7-Zip could not verify every multipart volume")
        result = subprocess.run([str(tool), "l", "-slt", "-ba", "--", str(archive)], capture_output=True,
                                text=True, timeout=180, check=True, stdin=subprocess.DEVNULL)
        for block in result.stdout.strip().split("\n\n"):
            fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
            name = fields.get("Path", "")
            parts = _member_parts(name)
            is_dir = fields.get("Folder") == "+" or fields.get("Attributes", "").startswith("D")
            if fields.get("Symbolic Link") or fields.get("Hard Link"):
                raise ValueError("Archive contains a link")
            digest = None
            if not is_dir:
                # Stream exactly one member. Disabling wildcards prevents a literal name from
                # accidentally selecting multiple items. No extraction paths are written.
                with subprocess.Popen([str(tool), "x", "-so", "-spd", "--", str(archive), name],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as proc:
                    digest = hashlib.file_digest(proc.stdout, "sha256").hexdigest()
                    if proc.wait() != 0:
                        raise ValueError(f"Could not decode archive member: {name}")
            records.append((parts, int(fields.get("Size") or 0), digest))
    if not any(digest for _, _, digest in records):
        raise ValueError("No verified extracted files")
    # Strip a wrapper only when the entire inventory is under that one folder.
    wrapped = all(parts[0] == folder.name for parts, _, _ in records)
    checked = set()
    for parts, size, expected in records:
        target = folder.joinpath(*(parts[1:] if wrapped else parts))
        if target in checked or target.resolve() != target.absolute() or not target.resolve().is_relative_to(folder.resolve()):
            raise ValueError(f"Ambiguous or linked archive member: {target}")
        checked.add(target)
        if expected is None:
            if not target.is_dir():
                raise ValueError(f"Missing directory: {target}")
            continue
        if not target.is_file() or target.stat().st_size != size:
            raise ValueError(f"Missing or changed extracted member: {target}")
        with target.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError(f"Extracted bytes differ: {target}")


def approval_snapshot(stamp: str, archive: Path) -> dict:
    csv_path = report_dir() / f"Archive_Peek_{stamp}.csv"
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if os.path.normcase(r.get("archive_path", "")) == os.path.normcase(str(archive))
                and r.get("verdict") == "MATCHES_EXTRACTED_FOLDER"]
    if len(rows) != 1 or not rows[0].get("extracted_folder"):
        raise ValueError("Run has no unique verified archive/sibling match")
    folder = archive.parent / rows[0]["extracted_folder"]
    from api.security import library_roots

    roots = [r.resolve() for r in library_roots() if archive.resolve().is_relative_to(r.resolve())]
    if not roots:
        raise ValueError("Archive is outside a configured library")
    root = max(roots, key=lambda p: len(p.parts))
    parts = {str(p): content_identity(p) for p in expand_multipart_set(archive)}
    _verify_folder(archive, folder, len(parts))
    return {"archive": str(archive), "root": str(root), "folder": str(folder), "parts": parts}
