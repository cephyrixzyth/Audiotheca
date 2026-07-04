#!/usr/bin/env python3
"""Build README walkthrough MP4s from captured screenshots using ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOT_DIR = ROOT / "docs" / "assets" / "screenshots"
VIDEO_DIR = ROOT / "docs" / "assets" / "videos"
TEMP_SRC = Path.home() / "AppData/Local/Temp/cursor/screenshots"

VIDEO_CLIPS: dict[str, list[str]] = {
    "first-scan-walkthrough.mp4": [
        "ui-overview.png",
        "scan-panel.png",
        "dashboard-gauges.png",
    ],
    "scan-phases-and-flow.mp4": ["scan-panel.png", "scan-panel.png"],
    "investigation-and-vendors.mp4": ["investigation-inbox.png", "duplicates-review.png"],
    "restructure-live-staging.mp4": ["restructure-preview.png", "archives-verdicts.png"],
    "file-explorer-and-archives.mp4": ["file-explorer.png", "archives-verdicts.png"],
    "ai-lookup-review.mp4": ["scan-panel.png", "investigation-inbox.png"],
    "security-and-space-recovery.mp4": ["security-malware.png", "environment-themes.png"],
}


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


def _build_clip(ffmpeg: str, images: list[Path], output: Path, *, seconds_per: float = 4.0) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    list_path = output.with_suffix(".txt")
    lines: list[str] = []
    for image in images:
        escaped = str(image).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
        lines.append(f"duration {seconds_per}")
    lines.append(f"file '{str(images[-1]).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'")
    list_path.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-vf",
            "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-movflags",
            "+faststart",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    list_path.unlink(missing_ok=True)


def main() -> None:
    ffmpeg = _ffmpeg()
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    if TEMP_SRC.is_dir():
        for png in TEMP_SRC.glob("*.png"):
            dest = SHOT_DIR / png.name
            shutil.copy2(png, dest)
            print(f"Copied {png.name}")

    for name, files in VIDEO_CLIPS.items():
        paths = [SHOT_DIR / file for file in files]
        missing = [p for p in paths if not p.is_file()]
        if missing:
            print(f"Skip {name}: missing {[p.name for p in missing]}", file=sys.stderr)
            continue
        out = VIDEO_DIR / name
        print(f"Building {name}…")
        _build_clip(ffmpeg, paths, out)

    print(f"Done. Videos in {VIDEO_DIR}")


if __name__ == "__main__":
    main()
