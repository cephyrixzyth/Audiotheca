"""Copy-on-write (reflink) dedupe — clone a keeper over a verified duplicate.

A reflink clone shares data blocks with its source like a hardlink saves
space, but each path stays its own file: editing, shredding or truncating one
copy never changes the other. That removes the whole class of shared-inode
bugs that hardlink dedupe invites, so reflinks are the default dedupe method
and hardlinks are an explicit opt-in.

Supported filesystems:
  * Linux — btrfs, XFS (reflink=1), bcachefs, OCFS2 via the FICLONE ioctl
  * macOS — APFS via clonefile(2)
  * Windows — ReFS / Dev Drive via FSCTL_DUPLICATE_EXTENTS_TO_FILE

Everything else (NTFS, ext4, ZFS without block cloning, SMB shares that do not
pass server-side clone through) reports ``supported=False`` and nothing is
changed.

CLI (used by generated space-recovery scripts):
  python -m audiotheca.reflink --keeper K --duplicate D --sha256 HEX
  python -m audiotheca.reflink --probe DIR
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import errno
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

FICLONE = 0x40049409  # _IOW(0x94, 9, int)
_HASH_CHUNK = 1024 * 1024


class ReflinkUnsupported(OSError):
    """The filesystem (or platform) cannot make copy-on-write clones."""


def _clone_linux(src: Path, dst: Path) -> None:
    import fcntl

    with open(src, "rb") as source, open(dst, "wb") as target:
        try:
            fcntl.ioctl(target.fileno(), FICLONE, source.fileno())
        except OSError as exc:
            if exc.errno in {errno.EOPNOTSUPP, errno.ENOTTY, errno.EINVAL, errno.EXDEV, errno.ENOSYS}:
                raise ReflinkUnsupported(exc.errno, f"Filesystem does not support reflinks: {exc.strerror}") from exc
            raise


def _clone_macos(src: Path, dst: Path) -> None:
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    clonefile = libc.clonefile
    clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clonefile.restype = ctypes.c_int
    if clonefile(os.fsencode(src), os.fsencode(dst), 0) != 0:
        err = ctypes.get_errno()
        if err in {errno.ENOTSUP, errno.EXDEV, errno.ENOSYS}:
            raise ReflinkUnsupported(err, "Filesystem does not support clonefile")
        raise OSError(err, os.strerror(err), str(dst))


def _clone_windows(src: Path, dst: Path) -> None:  # pragma: no cover - Windows only
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class DuplicateExtents(ctypes.Structure):
        _fields_ = [
            ("FileHandle", wintypes.HANDLE),
            ("SourceFileOffset", ctypes.c_longlong),
            ("TargetFileOffset", ctypes.c_longlong),
            ("ByteCount", ctypes.c_longlong),
        ]

    FSCTL_DUPLICATE_EXTENTS_TO_FILE = 0x00098344
    FSCTL_SET_SPARSE = 0x000900C4
    size = src.stat().st_size
    # ReFS clones in cluster-sized regions; the target must be pre-sized.
    with open(src, "rb") as source, open(dst, "wb") as target:
        import msvcrt

        src_handle = msvcrt.get_osfhandle(source.fileno())
        dst_handle = msvcrt.get_osfhandle(target.fileno())
        returned = wintypes.DWORD(0)
        kernel.DeviceIoControl(dst_handle, FSCTL_SET_SPARSE, None, 0, None, 0, ctypes.byref(returned), None)
        target.truncate(size)
        cluster = 64 * 1024
        offset = 0
        while offset < size:
            count = min(1024 * 1024 * 1024, ((size - offset + cluster - 1) // cluster) * cluster)
            params = DuplicateExtents(src_handle, offset, offset, count)
            ok = kernel.DeviceIoControl(
                dst_handle,
                FSCTL_DUPLICATE_EXTENTS_TO_FILE,
                ctypes.byref(params),
                ctypes.sizeof(params),
                None,
                0,
                ctypes.byref(returned),
                None,
            )
            if not ok:
                code = ctypes.get_last_error()
                # ERROR_INVALID_FUNCTION / ERROR_NOT_SUPPORTED → not ReFS
                if code in {1, 50}:
                    raise ReflinkUnsupported(code, "Volume does not support block cloning (ReFS required)")
                raise ctypes.WinError(code)
            offset += count
        target.truncate(size)


def clone_file(src: Path, dst: Path) -> None:
    """Create ``dst`` as a copy-on-write clone of ``src``. ``dst`` must not exist."""
    src, dst = Path(src), Path(dst)
    if os.path.lexists(dst):
        raise FileExistsError(errno.EEXIST, "Clone target already exists", str(dst))
    try:
        if sys.platform.startswith("linux"):
            _clone_linux(src, dst)
        elif sys.platform == "darwin":
            _clone_macos(src, dst)
        elif os.name == "nt":
            _clone_windows(src, dst)
        else:
            raise ReflinkUnsupported(errno.ENOSYS, f"Reflinks are not implemented on {sys.platform}")
    except BaseException:
        if sys.platform != "darwin":  # clonefile never leaves a partial target
            try:
                dst.unlink()
            except OSError:
                pass
        raise


def probe(directory: Path) -> dict[str, Any]:
    """Check whether ``directory``'s filesystem can clone, by cloning a scratch file."""
    directory = Path(directory)
    result: dict[str, Any] = {"path": str(directory), "supported": False, "reason": ""}
    if not directory.is_dir():
        result["reason"] = "Directory not found"
        return result
    try:
        with tempfile.TemporaryDirectory(prefix=".audiotheca-reflink-", dir=directory) as scratch:
            src = Path(scratch) / "probe.src"
            dst = Path(scratch) / "probe.dst"
            src.write_bytes(os.urandom(64 * 1024))
            clone_file(src, dst)
            if dst.read_bytes() != src.read_bytes():
                result["reason"] = "Clone verification failed"
                return result
            # Copy-on-write check: writing the clone must not change the source.
            original = src.read_bytes()
            with open(dst, "r+b") as handle:
                handle.write(b"\0" * 16)
            if src.read_bytes() != original:
                result["reason"] = "Clone shares writes with its source"
                return result
    except ReflinkUnsupported as exc:
        result["reason"] = str(exc.strerror or exc)
        return result
    except OSError as exc:
        result["reason"] = f"Probe failed: {exc}"
        return result
    result["supported"] = True
    result["reason"] = "Copy-on-write clones are available"
    return result


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def apply(keeper: Path, duplicate: Path, expected: str) -> dict[str, Any]:
    """Replace ``duplicate`` with a reflink clone of ``keeper``.

    Both files must still hash to ``expected``. The clone is built beside the
    duplicate, verified, then swapped in with an atomic rename, so a failure at
    any point leaves the duplicate untouched. The duplicate's permission bits
    and timestamps are carried over.
    """
    keeper, duplicate = Path(keeper), Path(duplicate)
    if keeper.is_symlink() or duplicate.is_symlink():
        raise ValueError("A symlink requires review")
    if not keeper.is_file() or not duplicate.is_file():
        raise FileNotFoundError("Keeper or duplicate is missing")
    if os.path.samefile(keeper, duplicate):
        raise ValueError("Keeper and duplicate are the same file (already hardlinked)")
    if _sha256(keeper) != expected:
        raise ValueError("Keeper changed since the plan")
    if _sha256(duplicate) != expected:
        raise ValueError("Duplicate changed since the plan")
    before = duplicate.stat()
    temp = duplicate.with_name(f".{duplicate.name}.reflink-{os.getpid()}")
    clone_file(keeper, temp)
    try:
        if _sha256(temp) != expected:
            raise OSError("Clone does not match the keeper")
        try:
            os.chmod(temp, before.st_mode & 0o7777)
            os.utime(temp, ns=(before.st_atime_ns, before.st_mtime_ns))
        except OSError:
            pass
        if hasattr(os, "chown") and os.name != "nt":
            try:
                os.chown(temp, before.st_uid, before.st_gid)
            except OSError:
                pass
        os.replace(temp, duplicate)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return {"keeper": str(keeper), "duplicate": str(duplicate), "method": "reflink", "bytes": before.st_size}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--probe", type=Path, help="report whether DIR supports reflinks")
    parser.add_argument("--keeper", type=Path)
    parser.add_argument("--duplicate", type=Path)
    parser.add_argument("--sha256")
    args = parser.parse_args(argv)
    if args.probe:
        result = probe(args.probe)
        print(("[OK] " if result["supported"] else "[--] ") + f"{result['path']}: {result['reason']}")
        return 0 if result["supported"] else 2
    if not (args.keeper and args.duplicate and args.sha256):
        parser.error("--keeper, --duplicate and --sha256 are required")
    try:
        apply(args.keeper, args.duplicate, args.sha256)
    except ReflinkUnsupported as exc:
        print(f"[SKIP] {args.duplicate}: {exc.strerror or exc}", file=sys.stderr)
        return 3
    except (OSError, ValueError) as exc:
        print(f"[FAIL] {args.duplicate}: {exc}", file=sys.stderr)
        return 1
    print(f"[CLONED] {args.duplicate} -> {args.keeper}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
