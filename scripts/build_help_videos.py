"""Build synthetic help videos from screenshot sequences (requires ffmpeg)."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "docs" / "assets" / "screenshots"
DEFAULT_OUTPUT = ROOT / "docs" / "assets" / "videos"


def _find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    return found


def build_video(
    input_dir: Path,
    output_path: Path,
    *,
    fps: int = 2,
    pattern: str = "*.png",
) -> dict[str, object]:
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg not found on PATH"}

    frames = sorted(input_dir.glob(pattern))
    if len(frames) < 2:
        return {"ok": False, "error": f"need at least 2 frames in {input_dir}"}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = output_path.with_suffix(".txt")
    lines = [f"file '{frame.resolve().as_posix()}'\nduration {1 / fps:.3f}" for frame in frames]
    lines.append(f"file '{frames[-1].resolve().as_posix()}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_file),
        "-vf",
        "scale=1280:-2",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        if list_file.is_file():
            list_file.unlink(missing_ok=True)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return {"ok": False, "error": err[:400] or f"ffmpeg exit {proc.returncode}"}

    return {"ok": True, "output": str(output_path), "frames": len(frames)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build help walkthrough MP4 from PNG screenshots")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "help-walkthrough.mp4")
    parser.add_argument("--fps", type=int, default=2)
    args = parser.parse_args()

    result = build_video(args.input, args.output, fps=args.fps)
    if not result.get("ok"):
        print(result.get("error"), file=sys.stderr)
        return 1
    print(f"Wrote {result['output']} ({result['frames']} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
