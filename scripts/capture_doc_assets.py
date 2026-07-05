#!/usr/bin/env python3
"""Seed demo library + reports and capture README screenshots/videos via Playwright."""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAMP = "20260704_1600"
LIB = ROOT / "docs" / "demo" / "library"
SEED_REPORTS = ROOT / "docs" / "demo" / "reports"
CAPTURE_HOME = ROOT / "docs" / "demo" / "capture_ws"
REPORTS = CAPTURE_HOME / "dedupe_reports"
SHOT_DIR = ROOT / "docs" / "assets" / "screenshots"
VIDEO_DIR = ROOT / "docs" / "assets" / "videos"
UI_PORT = int(os.environ.get("AUDIOTHECA_CAPTURE_UI_PORT", "5175"))
API_PORT = int(os.environ.get("AUDIOTHECA_CAPTURE_API_PORT", "8788"))
UI_URL = f"http://127.0.0.1:{UI_PORT}"
API_HEALTH = f"http://127.0.0.1:{API_PORT}/api/health"
VIEWPORT = {"width": 1920, "height": 1080}
TOKEN = "doc-capture-local-only"
FIRST_RUN_INIT = 'localStorage.setItem("audiotheca.firstRunComplete", "1");'

SCREENSHOT_PLAN: list[tuple[str, str]] = [
    ("ui-overview.png", "dashboard"),
    ("dashboard-gauges.png", "dashboard"),
    ("scan-panel.png", "scan"),
    ("investigation-inbox.png", "investigation"),
    ("duplicates-review.png", "duplicates"),
    ("restructure-preview.png", "restructure"),
    ("archives-verdicts.png", "archives"),
    ("security-malware.png", "security"),
    ("environment-themes.png", "environment"),
    ("help-panel.png", "help"),
    ("scene-renames.png", "scene-renames"),
    ("scan-audit.png", "scan-audit"),
    ("skipped-files.png", "skipped"),
]

VIDEO_CLIPS: list[tuple[str, list[str]]] = [
    ("first-scan-walkthrough.mp4", ["dashboard", "scan", "dashboard"]),
    ("scan-phases-and-flow.mp4", ["scan"]),
    ("investigation-and-vendors.mp4", ["investigation", "vendors"]),
    ("restructure-live-staging.mp4", ["restructure"]),
    ("file-explorer-and-archives.mp4", ["archives"]),
    ("ai-lookup-review.mp4", ["scan"]),
    ("security-and-space-recovery.mp4", ["security", "space-recovery"]),
]

REVIEW_TAB_IDS = frozenset(
    {"investigation", "duplicates", "restructure", "archives", "scene-renames", "scan-audit", "skipped"}
)
SYSTEM_TAB_IDS = frozenset({"space-recovery", "security", "environment", "vendors"})


DEMO_LIB_ROOT = Path("D:/Libraries/demo")


def _lib_path(*parts: str) -> str:
    """Display paths for doc screenshots (canonical demo library layout)."""
    return str(DEMO_LIB_ROOT.joinpath(*parts))


def seed_library() -> None:
    folders = [
        LIB / "a" / "AcmeAudio" / "SynthOne",
        LIB / "a" / "UnknownVendor" / "MysteryPack",
        LIB / "b" / "BetaSounds" / "DrumKit",
        LIB / "archives" / "redundant_extracted",
    ]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)
    (LIB / "a" / "AcmeAudio" / "SynthOne" / "readme.txt").write_text(
        "Acme Audio SynthOne v2.1\n", encoding="utf-8"
    )
    (LIB / "a" / "UnknownVendor" / "MysteryPack" / "product.nfo").write_text(
        "Unknown product pack\n", encoding="utf-8"
    )
    (LIB / "archives" / "redundant.rar").write_bytes(b"PK\x03\x04demo")
    (LIB / "archives" / "redundant_extracted" / "preset.fxp").write_bytes(b"\x00" * 64)


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def seed_reports() -> None:
    seed_library()
    SEED_REPORTS.mkdir(parents=True, exist_ok=True)

    summary = "\n".join(
        [
            "Engine version: 10.0.0",
            f"Run: {STAMP}",
            "DRY_RUN: true",
            "Scanned: 128 (cache hits: 4, failures: 1)",
            "Routes planned: 96",
            "Investigation: 12",
            "_unknown_vendor: 5",
            "_ambiguous_product: 3",
            "_needs_manual: 4",
            "Quarantined: 0",
            "Reconciled vendors: 18",
            "Vendor conflicts: 2",
            "Nested issues: 1",
            "Coexistence findings: 3",
            "Archive peek rows: 6",
            "Scene archive peeks: 2",
            "Scene renames planned: 2",
            "Errors: 0",
            "Duplicate groups (review): 3",
            "HIGH confidence: 2",
            "MEDIUM confidence: 1",
            "Coverage gaps: 2",
            "Cache hit paths: 4",
            "Probe truncations: 0",
            "Feedback skipped groups: 0",
        ]
    )
    (SEED_REPORTS / f"Run_Summary_{STAMP}.txt").write_text(summary, encoding="utf-8")

    inv_headers = [
        "Section",
        "Item Name",
        "Current Path",
        "Investigation Bucket",
        "Reason",
        "ID Method",
        "ID Confidence",
        "Fingerprint",
        "Size MB",
        "Planned Destination",
    ]
    inv_rows = [
        [
            "a",
            "MysteryPack",
            _lib_path("a", "UnknownVendor", "MysteryPack"),
            "_unknown_vendor",
            "no_vendor_match",
            "filename",
            "LOW",
            "fp-mystery",
            "240.5",
            "",
        ],
        [
            "a",
            "ObscureLib",
            _lib_path("a", "UnknownVendor", "ObscureLib"),
            "_unknown_vendor",
            "no_vendor_match",
            "nfo",
            "LOW",
            "fp-obscure",
            "88.2",
            "",
        ],
        [
            "b",
            "DrumKit",
            _lib_path("b", "BetaSounds", "DrumKit"),
            "_ambiguous_product",
            "multiple_products",
            "pe_header",
            "MEDIUM",
            "fp-drum",
            "512.0",
            _lib_path("b", "BetaSounds", "DrumKit"),
        ],
    ]
    _write_csv(SEED_REPORTS / f"Investigation_Breakdown_{STAMP}.csv", inv_headers, inv_rows)

    dup_headers = [
        "Dedup Key",
        "Confidence",
        "Group Kind",
        "Name Similarity %",
        "Size Ratio",
        "Content Check",
        "Index",
        "Item Name",
        "Section",
        "Full Path",
        "Vendor",
        "Size MB",
        "Recommendation",
        "Planned Action",
    ]
    dup_rows = [
        [
            "acme-synthone",
            "HIGH",
            "same_product",
            "98",
            "1.0",
            "hash_match",
            "1",
            "SynthOne",
            "a",
            _lib_path("a", "AcmeAudio", "SynthOne"),
            "Acme Audio",
            "120.4",
            "KEEP",
            "keep",
        ],
        [
            "acme-synthone",
            "HIGH",
            "same_product",
            "98",
            "1.0",
            "hash_match",
            "2",
            "SynthOne Copy",
            "a",
            _lib_path("a", "AcmeAudio", "SynthOne Copy"),
            "Acme Audio",
            "120.4",
            "DELETE",
            "delete_candidate",
        ],
    ]
    _write_csv(SEED_REPORTS / f"Duplicate_Review_{STAMP}.csv", dup_headers, dup_rows)

    restructure_headers = [
        "Section",
        "Item Name",
        "Current Path",
        "Planned Destination",
        "Vendor",
        "ID Method",
        "ID Confidence",
        "Clean Display Name",
        "Size MB",
        "Status",
        "Investigation Bucket",
    ]
    restructure_rows = [
        [
            "a",
            "SynthOne",
            _lib_path("a", "AcmeAudio", "SynthOne"),
            _lib_path("a", "Acme Audio", "SynthOne"),
            "Acme Audio",
            "nfo",
            "HIGH",
            "SynthOne",
            "120.4",
            "READY",
            "",
        ],
        [
            "b",
            "DrumKit",
            _lib_path("b", "BetaSounds", "DrumKit"),
            _lib_path("b", "Beta Sounds", "DrumKit"),
            "Beta Sounds",
            "pe_header",
            "HIGH",
            "DrumKit",
            "512.0",
            "NEEDS REVIEW",
            "",
        ],
    ]
    _write_csv(SEED_REPORTS / f"Restructure_Plan_{STAMP}.csv", restructure_headers, restructure_rows)

    audit_headers = [
        "Section",
        "Item Name",
        "Current Path",
        "Vendor",
        "ID Method",
        "ID Confidence",
        "Fingerprint",
        "Version Key",
        "Size MB",
        "Status",
        "Investigation Bucket",
        "Planned Destination",
        "Flags",
    ]
    audit_rows = [
        [
            "a",
            "SynthOne",
            _lib_path("a", "AcmeAudio", "SynthOne"),
            "Acme Audio",
            "nfo",
            "HIGH",
            "fp-synth",
            "v2.1",
            "120.4",
            "ROUTED",
            "",
            _lib_path("a", "Acme Audio", "SynthOne"),
            "",
        ],
        [
            "a",
            "MysteryPack",
            _lib_path("a", "UnknownVendor", "MysteryPack"),
            "",
            "filename",
            "LOW",
            "fp-mystery",
            "",
            "240.5",
            "INVESTIGATION",
            "_unknown_vendor",
            "",
            "ai_lookup",
        ],
    ]
    _write_csv(SEED_REPORTS / f"Scan_Audit_{STAMP}.csv", audit_headers, audit_rows)

    archive_headers = [
        "section",
        "item_name",
        "item_path",
        "archive_name",
        "archive_path",
        "extracted_folder",
        "name_similarity",
        "archive_size_mb",
        "verdict",
        "inferred_product",
    ]
    archive_rows = [
        [
            "archives",
            "redundant",
            _lib_path("archives"),
            "redundant.rar",
            _lib_path("archives", "redundant.rar"),
            _lib_path("archives", "redundant_extracted"),
            "0.95",
            "48.2",
            "MATCHES_EXTRACTED_FOLDER",
            "Demo Pack",
        ],
        [
            "archives",
            "mystery",
            _lib_path("archives"),
            "mystery.7z",
            _lib_path("archives", "mystery.7z"),
            "",
            "0.0",
            "12.0",
            "PEEK_ONLY",
            "Unknown",
        ],
    ]
    _write_csv(SEED_REPORTS / f"Archive_Peek_{STAMP}.csv", archive_headers, archive_rows)

    scene_headers = [
        "scene_id",
        "source_path",
        "proposed_name",
        "destination_path",
        "inferred_product",
        "multipart_diagnosis",
    ]
    scene_rows = [
        [
            "294335",
            _lib_path("a", "294335"),
            "VintageKeys",
            _lib_path("a", "VintageKeys"),
            "Vintage Keys",
            "complete",
        ],
    ]
    _write_csv(SEED_REPORTS / f"Scene_Rename_Plan_{STAMP}.csv", scene_headers, scene_rows)

    _write_csv(
        SEED_REPORTS / f"Scan_Failures_{STAMP}.csv",
        ["Section", "Item Name", "Full Path", "Error"],
        [
            [
                "a",
                "LockedPack",
                _lib_path("a", "UnknownVendor", "LockedPack"),
                "Access is denied",
            ],
        ],
    )
    _write_csv(
        SEED_REPORTS / f"Coverage_Gaps_{STAMP}.csv",
        ["Section", "Path", "Name", "Reason", "Detail"],
        [
            [
                "archives",
                _lib_path("archives", "loose.zip"),
                "loose.zip",
                "LOOSE_ARCHIVE",
                "Top-level archive outside item folder",
            ],
        ],
    )
    _write_csv(
        SEED_REPORTS / f"Cache_Hits_{STAMP}.csv",
        ["Section", "Path", "Name", "Mtime"],
        [
            [
                "a",
                _lib_path("a", "AcmeAudio", "SynthOne"),
                "SynthOne",
                "1710000000.0",
            ],
        ],
    )

    (SEED_REPORTS / f"Skip_Phase_Impact_{STAMP}.json").write_text(
        json.dumps({"archive_peek": {"count": 1, "detail": "demo skip impact"}}),
        encoding="utf-8",
    )

    REPORTS.mkdir(parents=True, exist_ok=True)
    for old in REPORTS.glob(f"*_{STAMP}.*"):
        old.unlink(missing_ok=True)
    for path in SEED_REPORTS.glob(f"*_{STAMP}.*"):
        shutil.copy2(path, REPORTS / path.name)
    (REPORTS / ".api_token").write_text(TOKEN, encoding="utf-8")


def _api_request(method: str, path: str, *, body: dict | None = None) -> None:
    import json as json_mod

    url = f"http://127.0.0.1:{API_PORT}{path}"
    data = json_mod.dumps(body or {}).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in {404, 409}:
            raise


def prepare_capture_session() -> None:
    """Isolated API with demo reports only — no live NAS scan banner."""
    try:
        _api_request(
            "POST",
            "/api/system/hard-reset",
            body={"keep_current_api": True, "kill_orphan_engines": True, "clear_artifacts": False},
        )
    except (TimeoutError, urllib.error.URLError, OSError):
        pass


def wait_url(url: str, *, timeout_s: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}")


def start_servers() -> tuple[subprocess.Popen[bytes] | None, subprocess.Popen[bytes] | None]:
    env = os.environ.copy()
    env["AUDIOTHECA_HOME"] = str(CAPTURE_HOME)
    env["AUDIOTHECA_LIBRARY_ROOTS"] = str(LIB)
    env["AUDIOTHECA_API_TOKEN"] = TOKEN
    env["AUDIOTHECA_ALLOW_REMOTE_TOKEN_BOOTSTRAP"] = "1"
    env["AUDIOTHECA_API_PORT"] = str(API_PORT)
    env["VITE_API_PORT"] = str(API_PORT)
    env["AUDIOTHECA_NO_RELOAD"] = "1"

    CAPTURE_HOME.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / ".api_token").write_text(TOKEN, encoding="utf-8")

    api_proc: subprocess.Popen[bytes] | None = None
    ui_proc: subprocess.Popen[bytes] | None = None

    try:
        wait_url(API_HEALTH, timeout_s=3.0)
    except RuntimeError:
        api_proc = subprocess.Popen(
            [sys.executable, "-m", "api.server"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    try:
        wait_url(UI_URL, timeout_s=3.0)
    except RuntimeError:
        ui_proc = subprocess.Popen(
            [
                "npm",
                "run",
                "dev",
                "--",
                "--host",
                "127.0.0.1",
                f"--port",
                str(UI_PORT),
                "--strictPort",
            ],
            cwd=ROOT / "ui",
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
        )

    wait_url(API_HEALTH)
    wait_url(UI_URL)
    prepare_capture_session()
    return api_proc, ui_proc


def stop_servers(api_proc: subprocess.Popen[bytes] | None, ui_proc: subprocess.Popen[bytes] | None) -> None:
    for proc in (ui_proc, api_proc):
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def _ffmpeg_available() -> bool:
    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except ImportError:
        return False


def _resolve_ffmpeg() -> str | None:
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return None


def _webm_to_mp4(webm: Path, mp4: Path) -> None:
    if not webm.is_file():
        return
    ffmpeg = _resolve_ffmpeg()
    if ffmpeg:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(webm),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(mp4),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        webm.unlink(missing_ok=True)
    else:
        mp4.write_bytes(webm.read_bytes())
        webm.rename(mp4.with_suffix(".webm"))


EDGE_PATHS = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Microsoft"
    / "Edge"
    / "Application"
    / "msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Google"
    / "Chrome"
    / "Application"
    / "chrome.exe",
]


def _browser_launch_kwargs() -> dict[str, object]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        for kwargs in (
            {"headless": True},
            {"headless": True, "channel": "msedge"},
            {"headless": True, "channel": "chrome"},
        ):
            try:
                browser = playwright.chromium.launch(**kwargs)
                browser.close()
                return kwargs
            except Exception:
                continue
        for candidate in EDGE_PATHS:
            if candidate.is_file():
                return {"headless": True, "executable_path": str(candidate)}
    return {"headless": True}


def capture() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
        from playwright.sync_api import sync_playwright

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

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

            def select_demo_run() -> None:
                run_select = page.locator("select.field-input").first
                run_select.wait_for(state="visible", timeout=15000)
                run_select.select_option(value=STAMP)
                page.wait_for_timeout(1200)
                if page.locator(".process-banner").count():
                    prepare_capture_session()
                    page.reload(wait_until="load")
                    page.wait_for_timeout(1200)
                    run_select.select_option(value=STAMP)
                    page.wait_for_timeout(800)

            select_demo_run()

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

            for filename, tab_id in SCREENSHOT_PLAN:
                shot(filename, tab_id)

            dismiss_explorer()
            click_tab("archives")
            page.locator('button.bucket-chip:has-text("All")').click()
            page.wait_for_timeout(600)
            diff_btn = page.get_by_role("button", name="Diff", exact=True).first
            if diff_btn.count():
                diff_btn.click()
                page.wait_for_timeout(1200)
                wizard = page.locator(".archive-diff-wizard").first
                if wizard.count():
                    wizard.screenshot(path=str(SHOT_DIR / "archive-diff-wizard.png"))

            # File explorer screenshot — after archives; close explorer when done
            dismiss_explorer()
            click_tab("investigation")
            page.get_by_role("button", name="Library", exact=False).click()
            page.wait_for_timeout(1500)
            explorer = page.locator(".file-explorer-shell").first
            if explorer.count():
                explorer.screenshot(path=str(SHOT_DIR / "file-explorer.png"))
            else:
                page.screenshot(path=str(SHOT_DIR / "file-explorer.png"), full_page=False)
            dismiss_explorer()

            # Videos — one context per clip
            for video_name, tabs in VIDEO_CLIPS:
                video_dir = VIDEO_DIR / "_tmp"
                video_dir.mkdir(parents=True, exist_ok=True)
                vctx = browser.new_context(
                    viewport=VIEWPORT,
                    record_video_dir=str(video_dir),
                    record_video_size=VIEWPORT,
                )
                vctx.add_init_script(FIRST_RUN_INIT)
                vpage = vctx.new_page()
                vpage.goto(UI_URL, wait_until="load")
                vpage.wait_for_timeout(1000)
                run_select = vpage.locator("select.field-input").first
                run_select.wait_for(state="visible", timeout=15000)
                run_select.select_option(value=STAMP)
                vpage.wait_for_timeout(800)
                for tab_id in tabs:
                    _click_tab(vpage, tab_id)
                    vpage.wait_for_timeout(1600)
                if "file-explorer" in video_name:
                    vpage.get_by_role("button", name="Library", exact=False).click()
                    vpage.wait_for_timeout(2000)
                    vpage.keyboard.press("Escape")
                vpage.close()
                vctx.close()
                webm_files = list(video_dir.glob("*.webm"))
                if webm_files:
                    target = VIDEO_DIR / video_name
                    _webm_to_mp4(webm_files[0], target)
                shutil.rmtree(video_dir, ignore_errors=True)

            browser.close()
    finally:
        stop_servers(api_proc, ui_proc)


def _tab_label(tab_id: str) -> str:
    labels = {
        "dashboard": "Dashboard",
        "scan": "Scan",
        "investigation": "Investigation",
        "duplicates": "Duplicates",
        "restructure": "Restructure",
        "archives": "Archives",
        "scene-renames": "Scene renames",
        "scan-audit": "Scan audit",
        "skipped": "Skipped",
        "space-recovery": "Space recovery",
        "security": "Security",
        "environment": "Environment",
        "vendors": "Vendors",
        "help": "Help",
    }
    return labels.get(tab_id, tab_id)


def _click_tab(page: object, tab_id: str) -> None:
    if tab_id in REVIEW_TAB_IDS:
        page.locator('button.top-tab:has-text("Review")').click()  # type: ignore[union-attr]
        page.wait_for_timeout(400)  # type: ignore[union-attr]
    elif tab_id in SYSTEM_TAB_IDS:
        page.locator('button.top-tab:has-text("System")').click()  # type: ignore[union-attr]
        page.wait_for_timeout(400)  # type: ignore[union-attr]
    page.locator(f'button.top-tab:has-text("{_tab_label(tab_id)}")').click()  # type: ignore[union-attr]
    page.wait_for_timeout(900)  # type: ignore[union-attr]


def main() -> None:
    print("Seeding demo library and reports…")
    seed_reports()
    print("Capturing screenshots and videos…")
    capture()
    print(f"Done. Screenshots: {SHOT_DIR}")
    print(f"Videos: {VIDEO_DIR}")


if __name__ == "__main__":
    main()
