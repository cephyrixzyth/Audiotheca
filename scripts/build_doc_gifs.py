#!/usr/bin/env python3
"""Convert docs walkthrough MP4s to optimized GIFs for the documentation."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEO_DIR = ROOT / "docs" / "assets" / "videos"
GIF_DIR = ROOT / "docs" / "assets" / "gifs"
GIF_WIDTH = 1000
GIF_FPS = 7


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError(
            "ffmpeg not found — install ffmpeg or run: pip install imageio-ffmpeg"
        ) from exc


def _mp4_to_gif(ffmpeg: str, source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    filter_chain = (
        f"fps={GIF_FPS},scale={GIF_WIDTH}:-1:flags=lanczos,"
        "split[s0][s1];[s0]palettegen=stats_mode=diff:max_colors=256[p];"
        "[s1][p]paletteuse=dither=bayer:bayer_scale=4"
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vf",
            filter_chain,
            "-loop",
            "0",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    ffmpeg = _ffmpeg()
    GIF_DIR.mkdir(parents=True, exist_ok=True)

    mp4s = sorted(p for p in VIDEO_DIR.glob("*.mp4") if p.is_file())
    if not mp4s:
        print(f"No MP4 files in {VIDEO_DIR}", file=sys.stderr)
    for mp4 in mp4s:
        out = GIF_DIR / f"{mp4.stem}.gif"
        print(f"Building {out.name}…")
        _mp4_to_gif(ffmpeg, mp4, out)
        size_mb = out.stat().st_size / (1024 * 1024)
        print(f"  -> {size_mb:.1f} MB")

    print(f"Done. GIFs in {GIF_DIR}")


if __name__ == "__main__":
    main()
