"""Generate desktop, mobile, container and browser icons from Audiotheca's master artwork."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"

def main():
    icons = UI / "src-tauri/icons"
    cli = UI / "node_modules/@tauri-apps/cli/tauri.js"
    if not cli.is_file():
        raise SystemExit("Run npm ci in ui to install the Tauri icon generator.")
    subprocess.run(["node", str(cli), "icon", str(UI / "brand/audiotheca.png"), "--output", str(icons)], cwd=UI, check=True)
    for name, target in (
        ("128x128@2x.png", ROOT / "deploy/unraid/icon.png"),
        ("128x128@2x.png", UI / "public/logo.png"),
        ("32x32.png", UI / "public/favicon.png"),
        ("icon.ico", UI / "public/favicon.ico"),
    ):
        shutil.copyfile(icons / name, target)

if __name__ == "__main__":
    main()
