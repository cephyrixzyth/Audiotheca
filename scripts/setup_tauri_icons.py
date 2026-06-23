"""Generate placeholder Tauri icons (run once before first `tauri build`)."""

from __future__ import annotations

import shutil
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "ui" / "src-tauri" / "icons"


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def write_png(path: Path, width: int, height: int, rgba: tuple[int, int, int, int]) -> None:
    r, g, b, a = rgba
    row = bytes([r, g, b, a]) * width
    raw = b"".join(b"\x00" + row for _ in range(height))
    compressed = zlib.compress(raw, 9)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", compressed)
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    color = (61, 127, 180, 255)  # accent blue
    base = ICON_DIR / "128x128.png"
    write_png(base, 128, 128, color)
    shutil.copyfile(base, ICON_DIR / "32x32.png")
    shutil.copyfile(base, ICON_DIR / "128x128@2x.png")
    shutil.copyfile(base, ICON_DIR / "icon.png")
    print(f"Wrote icons under {ICON_DIR}")
    print("After installing Rust, run: cd ui && cargo tauri icon src-tauri/icons/icon.png")


if __name__ == "__main__":
    main()
