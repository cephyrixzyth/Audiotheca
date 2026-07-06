#!/usr/bin/env python3
"""Capture only the two pending 1.0.2 screenshots (audio preview + dropzone)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from capture_doc_assets import (  # noqa: E402
    FIRST_RUN_INIT,
    SHOT_DIR,
    STAMP,
    UI_URL,
    VIEWPORT,
    _browser_launch_kwargs,
    _capture_extended_screenshots,
    _click_tab,
    seed_library,
    seed_reports,
    start_servers,
    stop_servers,
)


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright not installed")

    seed_library()
    seed_reports()
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    import os
    import subprocess
    import sys
    from capture_doc_assets import API_PORT, UI_PORT  # noqa: E402

    if sys.platform == "win32":
        for port in (API_PORT, UI_PORT):
            script = (
                f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | "
                "Select-Object -ExpandProperty OwningProcess -Unique | "
                "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                check=False,
            )
    os.environ.setdefault("AUDIOTHECA_CAPTURE_UI_PORT", str(UI_PORT))
    os.environ.setdefault("AUDIOTHECA_CAPTURE_API_PORT", str(API_PORT))

    api_proc, ui_proc = start_servers()
    launch_kwargs = _browser_launch_kwargs()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**launch_kwargs)
            context = browser.new_context(viewport=VIEWPORT)
            context.add_init_script(FIRST_RUN_INIT)
            page = context.new_page()
            page.goto(UI_URL, wait_until="load")
            page.wait_for_timeout(1500)

            run_select = page.locator("select.field-input").first
            run_select.wait_for(state="visible", timeout=15000)
            run_select.select_option(value=STAMP)
            page.wait_for_timeout(1200)

            def dismiss_explorer() -> None:
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
                close_btn = page.get_by_role("button", name="Close", exact=True)
                if close_btn.count():
                    close_btn.first.click()
                    page.wait_for_timeout(400)

            def click_tab(tab_id: str) -> None:
                _click_tab(page, tab_id)

            _capture_extended_screenshots(
                page,
                SHOT_DIR,
                click_tab=click_tab,
                dismiss_explorer=dismiss_explorer,
            )
            browser.close()
    finally:
        stop_servers(api_proc, ui_proc)

    pending = ["audio-preview.png", "dropzone-overlay.png"]
    missing = [name for name in pending if not (SHOT_DIR / name).is_file()]
    if missing:
        print(f"Still missing: {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Done — {SHOT_DIR}")


if __name__ == "__main__":
    main()
