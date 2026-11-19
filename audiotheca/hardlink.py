"""Apply one approved Windows hardlink under write-denying handles."""

import argparse
import ctypes
import hashlib
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _locked_input(path, *, may_retire=False):
    import msvcrt
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    open_file = kernel.CreateFileW
    open_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                          wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    open_file.restype = wintypes.HANDLE
    read, delete, share_read, open_existing = 0x80000000, 0x10000, 1, 3
    handle = open_file(str(path), read | (delete if may_retire else 0), share_read, None, open_existing, 0, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    with os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY), "rb") as stream:
        yield stream, handle


def apply(keeper: Path, duplicate: Path, expected: str) -> None:
    if os.name != "nt":
        raise OSError("This generated Windows plan requires Windows file sharing semantics")
    backup = duplicate.with_name(duplicate.name + ".linkbak")
    if keeper.is_symlink() or duplicate.is_symlink() or os.path.lexists(backup):
        raise ValueError("A link or existing backup requires review")
    with _locked_input(keeper) as (keep_stream, _):
        if hashlib.file_digest(keep_stream, "sha256").hexdigest() != expected:
            raise ValueError("Keeper changed since the plan")
        # Windows rename raises if the backup name was concurrently occupied.
        os.rename(duplicate, backup)
        try:
            with _locked_input(backup, may_retire=True) as (backup_stream, handle):
                if hashlib.file_digest(backup_stream, "sha256").hexdigest() != expected:
                    raise ValueError("Duplicate changed since the plan")
                os.link(keeper, duplicate)
                if not os.path.samefile(keeper, duplicate) or os.stat(keeper).st_nlink < 2:
                    raise OSError("Could not verify the new hardlink")
                # Delete the exact verified backup by its still-open handle. No writable
                # or rename-capable handle can coexist throughout the hash and link.
                from ctypes import wintypes
                dispose = ctypes.WinDLL("kernel32", use_last_error=True).SetFileInformationByHandle
                dispose.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
                flag = ctypes.c_ubyte(1)
                if not dispose(handle, 4, ctypes.byref(flag), ctypes.sizeof(flag)):
                    raise ctypes.WinError(ctypes.get_last_error())
        except (OSError, ValueError):
            if not os.path.lexists(duplicate):
                os.rename(backup, duplicate)
            # If a link or an intervening file occupies the name, retain the backup.
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keeper", type=Path, required=True)
    parser.add_argument("--duplicate", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    apply(args.keeper, args.duplicate, args.sha256)
