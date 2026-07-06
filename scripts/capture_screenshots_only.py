#!/usr/bin/env python3
"""Capture README screenshots only (no server start, no hard-reset, no videos)."""

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
    SCREENSHOT_PLAN,
    _browser_launch_kwargs,
    _capture_extended_screenshots,
    _click_tab,
)

UI_PORT = UI_URL.rsplit(":", 1)[-1]


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("playwright not installed")

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    launch_kwargs = _browser_launch_kwargs()

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

        def shot(name: str, tab_id: str) -> None:
            if tab_id == "archives":
                dismiss_explorer()
            click_tab(tab_id)
            if tab_id == "environment":
                page.locator("text=Themes").first.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
            if tab_id == "archives":
                page.locator('button.bucket-chip:has-text("All")').click()
                page.wait_for_timeout(600)
            if tab_id == "dashboard":
                page.wait_for_timeout(800)
            out = SHOT_DIR / name
            if name == "dashboard-gauges.png":
                target = page.locator(".dash-grid").first
                if not target.count():
                    target = page.locator(".dash").first
                if target.count():
                    target.screenshot(path=str(out))
                else:
                    page.screenshot(path=str(out), full_page=False)
            else:
                target = page.locator(".app-shell").first
                if target.count():
                    target.screenshot(path=str(out))
                else:
                    page.screenshot(path=str(out), full_page=False)
            print(f"  {name}")

        for filename, tab_id in SCREENSHOT_PLAN:
            shot(filename, tab_id)

        def shot_archive_diff_wizard() -> None:
            dismiss_explorer()
            click_tab("archives")
            page.locator('button.bucket-chip:has-text("All")').click()
            page.wait_for_timeout(600)
            diff_btn = page.get_by_role("button", name="Diff", exact=True).first
            if not diff_btn.count():
                print("  skip archive-diff-wizard.png (no Diff button)", file=sys.stderr)
                return
            diff_btn.click()
            page.wait_for_timeout(1200)
            wizard = page.locator(".archive-diff-wizard").first
            if wizard.count():
                wizard.screenshot(path=str(SHOT_DIR / "archive-diff-wizard.png"))
                print("  archive-diff-wizard.png")
            else:
                print("  skip archive-diff-wizard.png (wizard not visible)", file=sys.stderr)
            dismiss_explorer()

        shot_archive_diff_wizard()

        dismiss_explorer()
        click_tab("investigation")
        page.locator("button.top-tab-library").click()
        page.wait_for_timeout(1500)
        explorer = page.locator(".file-explorer-shell").first
        if explorer.count():
            explorer.screenshot(path=str(SHOT_DIR / "file-explorer.png"))
        else:
            page.screenshot(path=str(SHOT_DIR / "file-explorer.png"), full_page=False)
        print("  file-explorer.png")
        dismiss_explorer()

        _capture_extended_screenshots(
            page,
            SHOT_DIR,
            click_tab=click_tab,
            dismiss_explorer=dismiss_explorer,
        )

        browser.close()

    print(f"Done — {SHOT_DIR}")


if __name__ == "__main__":
    main()
