#!/usr/bin/env python3
"""SYN-GEN: seed a minimal demo library tree under docs/demo/ for walkthroughs."""

from __future__ import annotations

import argparse
import struct
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "demo" / "library"


def _write_min_wav(path: Path, *, duration_s: float = 0.25, rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(rate * duration_s)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        silence = struct.pack("<h", 0) * frames
        wf.writeframes(silence)


def seed_demo_library(*, force: bool = False) -> dict[str, int]:
    if DEMO.exists() and not force:
        existing = sum(1 for _ in DEMO.rglob("*") if _.is_file())
        return {"root": str(DEMO), "files": existing, "created": 0, "skipped": True}

    created = 0

    def touch(rel: str, content: str) -> None:
        nonlocal created
        target = DEMO / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created += 1

    touch(
        "a/AcmeAudio/SynthOne/readme.txt",
        "AcmeAudio SynthOne demo pack\nVersion 1.0\n",
    )
    touch(
        "a/UnknownVendor/MysteryPack/product.nfo",
        "Product: Mystery Pack\nGroup: DEMO\nDate: 2026-07-05\n",
    )
    touch("archives/redundant_extracted/preset.fxp", "FXP demo preset stub\n")

    wav_targets = [
        ("a/AcmeAudio/SynthOne/kick_120bpm_C.wav", 0.3, 44100),
        ("a/AcmeAudio/SynthOne/snare_120bpm.wav", 0.2, 48000),
        ("a/UnknownVendor/MysteryPack/ambience_loop.wav", 1.0, 44100),
    ]
    for rel, dur, rate in wav_targets:
        path = DEMO / rel
        if not path.is_file() or force:
            _write_min_wav(path, duration_s=dur, rate=rate)
            created += 1

    archive_stub = DEMO / "archives" / "redundant.rar"
    if not archive_stub.is_file() or force:
        archive_stub.parent.mkdir(parents=True, exist_ok=True)
        archive_stub.write_bytes(b"Rar!\x1a\x07\x00demo stub archive")
        created += 1

    return {"root": str(DEMO), "files": sum(1 for _ in DEMO.rglob("*") if _.is_file()), "created": created, "skipped": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed docs/demo/library walkthrough tree")
    parser.add_argument("--force", action="store_true", help="Rewrite demo files even if tree exists")
    args = parser.parse_args()
    result = seed_demo_library(force=args.force)
    print(f"SYN-GEN demo library at {result['root']}: {result['files']} files ({result['created']} created)")


if __name__ == "__main__":
    main()
