from __future__ import annotations

import re
import threading
import unittest
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from project_hub import server


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href" and value)


class ProjectHubTests(unittest.TestCase):
    def test_only_known_site_routes_resolve(self) -> None:
        for route in server.SITE_FILES:
            with self.subTest(route=route):
                self.assertIsNotNone(server.safe_site_file(route))
        for route in ("/../README.md", "/assets/../server.py", "/anything", "/api/status"):
            with self.subTest(route=route):
                self.assertIsNone(server.safe_site_file(route))

    def test_document_allowlist_contains_existing_repository_docs(self) -> None:
        for name, path in server.DOC_FILES.items():
            with self.subTest(name=name):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())

    def test_all_local_html_links_are_served_or_allowlisted(self) -> None:
        source_routes = {f"/source/{name}" for name in server.DOC_FILES}
        for page in Path(server.SITE).glob("*.html"):
            parser = LinkCollector()
            parser.feed(page.read_text(encoding="utf-8"))
            for href in parser.hrefs:
                if not href.startswith("/"):
                    continue
                route = re.split(r"[?#]", href, maxsplit=1)[0]
                with self.subTest(page=page.name, href=href):
                    self.assertTrue(route in server.SITE_FILES or route in source_routes)

    def test_status_summary_does_not_include_file_names_or_paths(self) -> None:
        status = server.project_status()
        self.assertEqual(set(status), {"branch", "commit", "changed_files", "checked_at"})
        self.assertNotIn("root", status)
        self.assertNotIn("files", status)

    def test_http_serves_hub_and_allowlisted_sources_only(self) -> None:
        app = server.make_server(port=0)
        thread = threading.Thread(target=app.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{app.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"Project hub", response.read())
            with urllib.request.urlopen(base + "/api/status", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b'"changed_files"', response.read())
            with urllib.request.urlopen(base + "/source/SECURITY.md", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"Threat model", response.read())
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base + "/source/.env", timeout=2)
            self.assertEqual(error.exception.code, 404)
            request = urllib.request.Request(base + "/", headers={"Host": "example.com"})
            with self.assertRaises(urllib.error.HTTPError) as host_error:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(host_error.exception.code, 400)
        finally:
            app.shutdown()
            app.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
