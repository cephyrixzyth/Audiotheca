"""Verified cross-volume moves. Reserve private work directories on both filesystems."""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
import subprocess
import tempfile
from pathlib import Path

from audiotheca.file_integrity import content_identity


def object_id(path: Path) -> list[int]:
    info = path.lstat()
    return [info.st_dev, info.st_ino]


def rename_exclusive(src: Path, dst: Path) -> None:
    """Rename without replacing an intervening directory entry."""
    if os.name == "nt":
        os.rename(src, dst)
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin" and hasattr(libc, "renamex_np"):
        result = libc.renamex_np(os.fsencode(src), os.fsencode(dst), 4)  # RENAME_EXCL
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        result = libc.renameat2(-100, os.fsencode(src), -100, os.fsencode(dst), 1)  # RENAME_NOREPLACE
    else:
        raise OSError("Filesystem lacks an exclusive rename primitive")
    if result:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(dst))


def matches(path: Path, identity: str, expected_id: list[int] | None) -> bool:
    return bool(expected_id and os.path.lexists(path) and object_id(path) == expected_id
                and content_identity(path) == identity)


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    import errno
    fd = os.open(path, os.O_RDONLY)
    try:
        try:
            os.fsync(fd)
        except OSError as exc:
            if exc.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
    finally:
        os.close(fd)


def _copy(src: Path, target: Path) -> None:
    if sys.platform == "darwin":
        # Preserve resource forks, Finder metadata and extended attributes where the
        # target filesystem supports them. Failed native copies retain the source.
        result = subprocess.run(["/usr/bin/ditto", "--rsrc", "--extattr", str(src), str(target)], capture_output=True)
        if result.returncode:
            raise OSError(result.stderr.decode(errors="replace").strip() or "macOS copy failed")
    elif src.is_dir():
        shutil.copytree(src, target, symlinks=True, copy_function=shutil.copy2)
    else:
        shutil.copy2(src, target, follow_symlinks=False)
    if src.is_dir():
        for directory, _, files in os.walk(target, topdown=False):
            for name in files:
                path = Path(directory) / name
                if not path.is_symlink():
                    with path.open("rb") as stream:
                        os.fsync(stream.fileno())
            _sync_directory(Path(directory))
    else:
        # Windows rejects fsync on a read-only handle (EBADF). Flush through a
        # writable handle so the copied payload is durable on Windows and POSIX.
        with target.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())


def _remove_copy(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _remove_empty(workdir: Path) -> None:
    try:
        workdir.rmdir()
    except OSError:
        pass


def _can_retire(held: Path) -> bool:
    # The name is private after the exclusive rename. Preserve the old inode when an
    # editor already has it open, or when this host cannot inspect local open handles.
    if os.name == "nt":
        from audiotheca.hardlink import _locked_input
        try:
            files = (p for p in held.rglob("*") if p.is_file()) if held.is_dir() else [held]
            for path in files:
                with _locked_input(path):
                    pass
        except OSError:
            return False
        return True
    lsof = shutil.which("lsof")
    if not lsof:
        return False
    selector = ["+D", str(held)] if held.is_dir() else ["--", str(held)]
    try:
        result = subprocess.run([lsof, "-nP", "-t", *selector], capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 1 and not result.stdout and not result.stderr


def transfer(src: Path, dst: Path, identity: str, src_id: list[int], record) -> list[int]:
    """Copy, verify, atomically publish and reconcile source ownership before retiring the original."""
    dest_dir = Path(tempfile.mkdtemp(prefix=".audiotheca-copy-", dir=dst.parent))
    temp = dest_dir / "payload"
    try:
        source_dir = Path(tempfile.mkdtemp(prefix=".audiotheca-move-", dir=src.parent))
    except OSError:
        _remove_empty(dest_dir)
        raise
    held = source_dir / "original"
    receipt = {"source": str(src), "destination": str(dst), "held": str(held), "temp": str(temp),
               "source_id": src_id, "copy_id": None, "temp_dir_id": object_id(dest_dir)}
    published = False
    try:
        record(receipt)
        _copy(src, temp)
        if content_identity(temp) != identity or not matches(src, identity, src_id):
            raise ValueError("Source changed while copying across volumes")
        receipt["copy_id"] = object_id(temp)
        record(receipt)
        # Claim the original name atomically. If another object replaced it, return that
        # exact object to its original location. An occupied restore location is never overwritten.
        rename_exclusive(src, held)
        _sync_directory(src.parent)
        if not matches(held, identity, src_id):
            raise ValueError("Original changed before publication")
        rename_exclusive(temp, dst)
        _sync_directory(dst.parent)
        published = True
        if not matches(dst, identity, receipt["copy_id"]) or not matches(held, identity, src_id):
            raise ValueError("Contents changed during publication; both copies retained")
        try:
            if _can_retire(held) and matches(held, identity, src_id):
                _remove_copy(held)
            else:
                record({**receipt, "cleanup_error": f"Original retained for an open file or unverified cleanup: {held}"})
        except OSError as exc:
            record({**receipt, "cleanup_error": str(exc)})
        return receipt["copy_id"]
    except (OSError, ValueError):
        if os.path.lexists(held) and not os.path.lexists(src):
            rename_exclusive(held, src)
            _sync_directory(src.parent)
        # A published destination is never deleted on error. Its verified source, or a
        # changed original, remains at the source path or recorded holding path for review.
        raise
    finally:
        if not published and os.path.lexists(temp):
            _remove_copy(temp)
        _remove_empty(dest_dir)
        _remove_empty(source_dir)


def interrupted_outcome(receipt: dict, identity: str, *, apply: bool) -> str:
    """Reconcile a crash using recorded inode and content evidence. Return either endpoint's name."""
    src, dst = Path(receipt["source"]), Path(receipt["destination"])
    held = Path(receipt["held"])
    temp = Path(receipt["temp"])
    def clean_private_temp():
        if apply and temp.parent.exists() and object_id(temp.parent) == receipt.get("temp_dir_id"):
            if os.path.lexists(temp):
                _remove_copy(temp)
            _remove_empty(temp.parent)
    if os.path.lexists(src):
        if matches(src, identity, receipt["source_id"]) and not os.path.lexists(dst) and not os.path.lexists(held):
            clean_private_temp()
            return "source"
        raise ValueError(f"Transfer has conflicting endpoints. Inspect {src}, {dst} and {held}")
    if matches(dst, identity, receipt.get("copy_id")):
        if os.path.lexists(held) and not matches(held, identity, receipt["source_id"]):
            raise ValueError(f"Staged bytes survived; a second version remains at {held}")
        # Retain a surviving held copy from an interrupted cleanup. It can contain files
        # still open by another application and is documented in the ledger.
        return "destination"
    if not os.path.lexists(dst) and matches(held, identity, receipt["source_id"]):
        if apply:
            rename_exclusive(held, src)
            _sync_directory(src.parent)
            _remove_empty(held.parent)
            clean_private_temp()
        return "source"
    raise ValueError(f"Transfer needs manual reconciliation: {src}, {dst}, {held}")
