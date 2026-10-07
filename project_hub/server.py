"""Serve the read-only Audiotheca project hub on loopback."""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SITE = Path(__file__).resolve().parent / "site"
PORT = 6129
SITE_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/roadmap.html": "roadmap.html",
    "/quality.html": "quality.html",
    "/docs.html": "docs.html",
    "/changes.html": "changes.html",
    "/assets/theme.css": "theme.css",
    "/assets/hub.js": "hub.js",
}
DOC_FILES = {
    "README.md": ROOT / "README.md",
    "CHANGELOG.md": ROOT / "docs" / "CHANGELOG.md",
    "ROADMAP_REMAINING.md": ROOT / "docs" / "ROADMAP_REMAINING.md",
    "SECURITY.md": ROOT / "docs" / "SECURITY.md",
    "TESTING.md": ROOT / "docs" / "TESTING.md",
    "INSTALL.md": ROOT / "docs" / "INSTALL.md",
    "SPEC_CATALOG.md": ROOT / "docs" / "SPEC_CATALOG.md",
    "SOURCES.md": ROOT / "docs" / "SOURCES.md",
    "USER_GUIDE.md": ROOT / "docs" / "USER_GUIDE.md",
    "PHASED_ROADMAP.md": ROOT / "docs" / "PHASED_ROADMAP.md",
    "ARCHITECTURE_AND_UI_ROADMAP.md": ROOT / "docs" / "ARCHITECTURE_AND_UI_ROADMAP.md",
    "PROJECT_HUB.md": ROOT / "docs" / "PROJECT_HUB.md",
}


def project_status() -> dict[str, object]:
    """Return a small status summary without exposing filenames or environment data."""
    result: dict[str, object] = {
        "branch": "unavailable",
        "commit": "unavailable",
        "changed_files": None,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        branch = subprocess.run(
            ["git", "-C", str(ROOT), "branch", "--show-current"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        status = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True, text=True, timeout=3, check=False,
        )
        if branch.returncode == head.returncode == status.returncode == 0:
            result.update({
                "branch": branch.stdout.strip() or "detached",
                "commit": head.stdout.strip(),
                "changed_files": sum(bool(line.strip()) for line in status.stdout.splitlines()),
            })
    except (OSError, subprocess.SubprocessError):
        pass
    return result


def safe_site_file(route: str) -> Path | None:
    """Resolve only named, bundled assets; never accept arbitrary paths."""
    name = SITE_FILES.get(route)
    if name is None:
        return None
    candidate = SITE / name
    if candidate.is_symlink() or not candidate.is_file():
        return None
    try:
        candidate.resolve(strict=True).relative_to(SITE.resolve(strict=True))
    except (OSError, ValueError):
        return None
    return candidate


class Handler(BaseHTTPRequestHandler):
    server_version = "AudiothecaProjectHub/1.0"
    sys_version = ""

    def _allowed_host(self) -> bool:
        host = self.headers.get("Host", "").lower()
        port = self.server.server_address[1]
        return host in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._allowed_host():
            self._send(b"Host not allowed", "text/plain; charset=utf-8", 400)
            return
        route = unquote(urlsplit(self.path).path)
        if route == "/api/status":
            body = json.dumps(project_status(), separators=(",", ":")).encode("utf-8")
            self._send(body, "application/json; charset=utf-8")
            return
        if route.startswith("/source/"):
            key = route.removeprefix("/source/")
            source = DOC_FILES.get(key)
            if source is None or source.is_symlink() or not source.is_file():
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            try:
                source.resolve(strict=True).relative_to(ROOT.resolve(strict=True))
                contents = source.read_bytes()
            except (OSError, ValueError):
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            self._send(contents, "text/markdown; charset=utf-8")
            return
        asset = safe_site_file(route)
        if asset is None:
            self._send(b"Not found", "text/plain; charset=utf-8", 404)
            return
        content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript"}:
            content_type += "; charset=utf-8"
        self._send(asset.read_bytes(), content_type)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        if not self._allowed_host() or safe_site_file(unquote(urlsplit(self.path).path)) is None:
            self._send(b"Not found", "text/plain; charset=utf-8", 404)
            return
        asset = safe_site_file(unquote(urlsplit(self.path).path))
        assert asset is not None
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(asset.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(asset.stat().st_size))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep local access logs minimal and avoid logging query-string content.
        print(f"[hub] {self.address_string()} {self.command} {urlsplit(self.path).path} {args[1] if len(args) > 1 else ''}")


def make_server(port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    try:
        app = make_server()
    except OSError as exc:
        raise SystemExit(f"Could not start Audiotheca Project Hub on 127.0.0.1:{PORT}: {exc}") from exc
    print(f"Audiotheca Project Hub: http://127.0.0.1:{PORT}/", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.server_close()


if __name__ == "__main__":
    main()
