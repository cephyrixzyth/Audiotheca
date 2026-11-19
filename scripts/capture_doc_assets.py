#!/usr/bin/env python3
"""Capture the real UI against an isolated fixture library and an isolated API."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen
import wave
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def seed(directory: Path) -> Path:
    library = directory / "Sound Library"
    reports = directory / "Application data" / "dedupe_reports"
    shutil.copytree(ROOT / "docs/demo/library", library)
    shutil.copytree(ROOT / "docs/demo/reports", reports)
    for file in reports.glob("*.csv"):
        with file.open(encoding="utf-8-sig", newline="") as src:
            records = list(csv.reader(src))
        for row in records:
            for ix, value in enumerate(row):
                if value.lower().replace("\\", "/").startswith("d:/libraries/demo"):
                    suffix = value.replace("\\", "/")[len("D:/Libraries/demo"):].strip("/")
                    row[ix] = str(library / suffix)
                if "redundant.rar" in row[ix]:
                    row[ix] = row[ix].replace("redundant.rar", "redundant.zip")
        with file.open("w", newline="", encoding="utf-8") as dst:
            csv.writer(dst).writerows(records)
    (library / "b/BetaSounds/DrumKit").mkdir(parents=True, exist_ok=True)
    synth = library / "a/AcmeAudio/SynthOne"
    rate = 22050
    wav = synth / "kick_120bpm_C.wav"
    with wave.open(str(wav), "wb") as target:
        target.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        samples = bytearray()
        for frame in range(rate * 4):
            t = frame / rate
            phase = t % .5
            pulse = math.exp(-phase * 13)
            value = int(21500 * pulse * math.sin(2 * math.pi * (58 * t - .09 * math.exp(-phase * 35))))
            samples.extend(struct.pack("<h", value))
        target.writeframes(samples)
    sibling = library / "archives/redundant_extracted"
    (sibling / "Drums").mkdir(exist_ok=True)
    shutil.copyfile(wav, sibling / "Drums/Kick.wav")
    (library / "archives/redundant.rar").unlink(missing_ok=True)
    with zipfile.ZipFile(library / "archives/redundant.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for member in sorted(sibling.rglob("*")):
            if member.is_file():
                archive.write(member, member.relative_to(sibling))
    return library


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_url(url: str, process: subprocess.Popen) -> None:
    for _ in range(900):
        if process.poll() is not None:
            raise RuntimeError(f"Capture server exited with {process.returncode}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(.2)
    raise RuntimeError(f"Capture server did not become ready at {url}")


def main(only: str = "") -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets")
    parser.add_argument("--only", default=only, help="Comma-separated asset stems, or screenshots")
    parser.add_argument("--serve", type=Path, help="Write private fixture connection details here and serve until stopped")
    parser.add_argument("--proof", type=Path, help="Write the action and asset validation ledger here")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="Audiotheca-Demo-", dir="/tmp" if sys.platform != "win32" else None) as tmp:
        work = Path(tmp)
        library = seed(work)
        api_port, ui_port = free_port(), free_port()
        while ui_port == api_port:
            ui_port = free_port()
        settings = dict(os.environ, AUDIOTHECA_HOME=str(work / "Application data"),
                        AUDIOTHECA_LIBRARY_ROOT=str(library), AUDIOTHECA_LIBRARY_ROOTS=str(library),
                        AUDIOTHECA_API_HOST="127.0.0.1", AUDIOTHECA_API_PORT=str(api_port),
                        AUDIOTHECA_NO_RELOAD="1", AUDIOTHECA_AI_LOOKUP_PROVIDER="stub",
                        AUDIOTHECA_VITE_CACHE=str(work / "vite-cache"),
                        VITE_API_PORT=str(api_port), VITE_DEFAULT_LIBRARY_ROOT=str(library))
        for key in ("AUDIOTHECA_API_TOKEN", "AUDIOTHECA_REPORTS_DIR", "AUDIOTHECA_DATA_DIR"):
            settings.pop(key, None)
        processes = []
        try:
            api = subprocess.Popen([sys.executable, "-c", "from api.server import main; main()"], cwd=ROOT, env=settings, stdout=sys.stderr, stderr=sys.stderr)
            processes.append(api)
            # Serve an immutable production build so development edits and HMR cannot enter a recording.
            dist = work / "web"
            vite_bin = ["node", "node_modules/vite/bin/vite.js"]
            subprocess.run([*vite_bin, "build", "--outDir", str(dist)], cwd=ROOT / "ui", env=settings,
                           stdout=sys.stderr, stderr=sys.stderr, check=True)
            vite = subprocess.Popen([*vite_bin, "preview", "--outDir", str(dist), "--host", "127.0.0.1",
                                     "--port", str(ui_port), "--strictPort"], cwd=ROOT / "ui", env=settings,
                                    stdout=sys.stderr, stderr=sys.stderr)
            processes.append(vite)
            origin = f"http://127.0.0.1:{ui_port}"
            wait_url(f"http://127.0.0.1:{api_port}/api/health", api)
            wait_url(origin, vite)
            config = dict(origin=origin, lib=str(library), workspace=str(work), only=args.only)
            if args.serve:
                args.serve.write_text(json.dumps(config))
                print(origin, flush=True)
                signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
                while all(p.poll() is None for p in processes):
                    time.sleep(.5)
                return
            stage = work / "capture"
            config.update(output=str(stage))
            config_file = work / "capture.json"
            config_file.write_text(json.dumps(config))
            subprocess.run(["node", "scripts/capture-help.mjs", str(config_file)], cwd=ROOT / "ui", check=True)
            for folder in ("screenshots", "videos", "gifs"):
                target = args.output / folder
                target.mkdir(parents=True, exist_ok=True)
                for file in sorted((stage / folder).glob("*")):
                    shutil.copy2(file, target / file.name)
            if args.proof:
                shutil.copy2(stage / "capture-proof.json", args.proof)
        finally:
            for p in reversed(processes):
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()


if __name__ == "__main__":
    main()
