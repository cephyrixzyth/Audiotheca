"""Harvest vendor/product names from web sources into a research inbox.

Scraped names land in vendor_harvest_candidates.json only. They are NOT used by
the scan engine until you explicitly add them to vendor_overrides.json (via Approve
in the UI or add_user_vendor). Built-in vendor_db.py is never modified by harvest.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from api.paths import report_dir
from audiotheca.local_storage import serialized_store, write_json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from audiotheca.config import KEYWORD_BLOCKLIST
from audiotheca.vendor_overrides import add_user_vendor, load_user_vendors
from vendor_db import VENDOR_DATABASE

FEEDBACK_DIR = report_dir() / "feedback"
CANDIDATES_PATH = FEEDBACK_DIR / "vendor_harvest_candidates.json"

USER_AGENT = "Audiotheca-VendorHarvest/1.0 (+local library organizer)"
FETCH_DELAY_S = 1.5

# Categories for harvested vendors (maps to vendor_db groups + extensions for stems/bootlegs)
HARVEST_CATEGORIES = [
    "DAW_Ecosystems",
    "Plugin_FX_Mixing_Mastering",
    "Synths_Instruments",
    "Cinematic_Orchestral",
    "Drums_Guitar_Band",
    "SFX_Foley_Post",
    "Sample_Packs_Loops",
    "Stems_Multitracks",
    "Bootleg_Collections",
    "Mixing_Engineering",
    "User_Added",
]

DEFAULT_SEED_URLS = [
    "https://www.kvraudio.com/forum/index.php?sid=3e49a24a889c05889d46cf5f9accdcc3",
    "https://www.kvraudio.com/forum/viewtopic.php?t=353321",
    "https://www.reddit.com/r/musicproduction/",
    "https://sfx-resource.fandom.com/wiki/List_of_Sound_Ideas_Libraries",
    "https://sounddogs.com/",
]

STEM_BOOTLEG_SEED_URLS = [
    "https://www.reddit.com/r/MultiTracks/",
    "https://www.reddit.com/r/Trackstacks/",
    "https://www.reddit.com/r/audioengineering/",
    "https://www.kvraudio.com/forum/viewforum.php?f=1",
    "https://www.gearsspace.com/board/forums/studio-live-sound.17/",
]

MIXING_ENGINEER_SEED_URLS = [
    "https://www.reddit.com/r/mixingmastering/",
    "https://www.reddit.com/r/audioengineering/",
    "https://www.kvraudio.com/forum/viewforum.php?f=15",
    "https://www.soundonsound.com/techniques",
]

VI_CONTROL_SEED_URLS = [
    "https://vi-control.net/community/",
    "https://vi-control.net/community/forums/sample-library-discussion.27/",
    "https://vi-control.net/community/forums/kontakt.29/",
]

KVR_SEED_URLS = [
    "https://www.kvraudio.com/forum/viewforum.php?f=1",
    "https://www.kvraudio.com/forum/viewforum.php?f=15",
    "https://www.kvraudio.com/forum/viewtopic.php?t=353321",
]

HARVEST_SOURCE_PRESETS: list[dict[str, object]] = [
    {
        "id": "user_seeds",
        "label": "Your sites (KVR, Reddit, SFX wiki, Sounddogs)",
        "urls": DEFAULT_SEED_URLS,
        "default_category": "User_Added",
        "notes": "Research inbox only — pick names to add to your vendor base.",
    },
    {
        "id": "kvr",
        "label": "KVR Audio forums",
        "urls": KVR_SEED_URLS,
        "default_category": "KVR_Research",
        "notes": "Plugin/sample vendor names from KVR threads → approve into vendor_overrides.",
    },
    {
        "id": "vi_control",
        "label": "vi-control (Kontakt / sample libraries)",
        "urls": VI_CONTROL_SEED_URLS,
        "default_category": "VI_Control_Research",
        "notes": "Library/vendor naming from vi-control.net — research only until approved.",
    },
    {
        "id": "stems_bootleg",
        "label": "Stems / multitrack naming indexes (reference)",
        "urls": STEM_BOOTLEG_SEED_URLS,
        "default_category": "Stems_Multitracks",
        "notes": "Band/artist naming hints for your library — not auto-routed until added.",
    },
    {
        "id": "mixing_engineers",
        "label": "Mixing engineer forums (reference)",
        "urls": MIXING_ENGINEER_SEED_URLS,
        "default_category": "Mixing_Engineering",
        "notes": "Tool/site names for research — optional vendor additions.",
    },
]

NOISE_WORDS = {
    "forum",
    "topic",
    "thread",
    "reply",
    "post",
    "view",
    "login",
    "register",
    "search",
    "wiki",
    "edit",
    "category",
    "home",
    "about",
    "contact",
    "privacy",
    "terms",
    "reddit",
    "subreddit",
    "comments",
    "share",
    "save",
    "hide",
    "report",
    "more",
    "less",
    "read",
    "click",
    "here",
    "page",
    "next",
    "previous",
    "index",
    "list",
    "sound",
    "audio",
    "music",
    "production",
    "library",
    "libraries",
    "series",
    "volume",
    "edition",
    "collection",
    "pack",
    "sample",
    "samples",
    "free",
    "download",
    "official",
    "website",
    "http",
    "https",
    "www",
    "com",
    "org",
    "net",
}

TITLE_SPLIT_RE = re.compile(r"\s[-–—|:]\s")
BRACKET_RE = re.compile(r"^\[(.+?)\]")
VERSION_RE = re.compile(r"\b(v?\d+(\.\d+)+|v\d+)\b", re.I)
PAREN_RE = re.compile(r"\([^)]*\)")
HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class HarvestCandidate:
    harvest_id: str
    company: str
    keywords: list[str]
    category: str
    source_url: str
    source_label: str
    confidence: str
    notes: str
    status: str = "pending"
    already_known: bool = False
    created: str = ""

    def to_dict(self) -> dict:
        return {
            "harvest_id": self.harvest_id,
            "company": self.company,
            "keywords": self.keywords,
            "category": self.category,
            "source_url": self.source_url,
            "source_label": self.source_label,
            "confidence": self.confidence,
            "notes": self.notes,
            "status": self.status,
            "already_known": self.already_known,
            "created": self.created,
        }


@dataclass
class HarvestResult:
    url: str
    source_label: str
    ok: bool
    candidates_found: int = 0
    error: str = ""
    fetch_ms: int = 0


class _TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.list_items: list[str] = []
        self.table_cells: list[str] = []
        self.headings: list[str] = []
        self.title: str = ""
        self._in_title = False
        self._in_a = False
        self._link_href = ""
        self._in_li = False
        self._in_td = False
        self._in_th = False
        self._in_h = False
        self._buf = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
            self._buf = ""
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            self._buf = ""
            self._link_href = href
            self._in_a = True
        elif tag == "li":
            self._in_li = True
            self._buf = ""
        elif tag in {"td", "th"}:
            self._in_td = tag == "td"
            self._in_th = tag == "th"
            self._buf = ""
        elif tag in {"h1", "h2", "h3", "h4"}:
            self._in_h = True
            self._buf = ""

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        text = self._clean(self._buf)
        if tag == "title" and self._in_title:
            self.title = text
            self._in_title = False
        elif tag == "a" and self._in_a:
            if text:
                self.links.append((text, self._link_href))
            self._in_a = False
        elif tag == "li" and self._in_li:
            if text:
                self.list_items.append(text)
            self._in_li = False
        elif tag in {"td", "th"} and (self._in_td or self._in_th):
            if text:
                self.table_cells.append(text)
            self._in_td = False
            self._in_th = False
        elif tag in {"h1", "h2", "h3", "h4"} and self._in_h:
            if text:
                self.headings.append(text)
            self._in_h = False
        self._buf = ""

    def handle_data(self, data: str) -> None:
        if any(
            (
                self._in_title,
                self._in_a,
                self._in_li,
                self._in_td,
                self._in_th,
                self._in_h,
            )
        ):
            self._buf += data

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _known_vendor_set() -> set[str]:
    known: set[str] = set()
    for group in VENDOR_DATABASE.values():
        for name in group:
            known.add(name.lower())
            for kw in group[name]:
                if len(kw) >= 4:
                    known.add(kw.lower())
    for row in load_user_vendors():
        known.add(row.company.lower())
        for kw in row.keywords:
            known.add(kw.lower())
    return known


def fetch_page(url: str, *, timeout: float = 30.0) -> tuple[str, int]:
    from runtime_policy import require_outbound

    require_outbound("vendor harvest")
    started = time.monotonic()
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    elapsed = int((time.monotonic() - started) * 1000)
    charset = "utf-8"
    text = raw.decode(charset, errors="replace")
    return text, elapsed


def parse_html(html: str) -> _TextCollector:
    parser = _TextCollector()
    parser.feed(html)
    return parser


def _normalize_company(name: str) -> str:
    name = HTML_TAG_RE.sub("", name)
    name = PAREN_RE.sub("", name)
    name = VERSION_RE.sub("", name)
    name = re.sub(r"\s+", " ", name).strip(" -–—|:")
    if not name:
        return ""
    if len(name) > 80:
        name = name[:80].rsplit(" ", 1)[0]
    return name


def _keywords_for(company: str, extra: list[str] | None = None) -> list[str]:
    words: list[str] = []
    base = company.lower().strip()
    if base and base not in KEYWORD_BLOCKLIST and len(base) >= 3:
        words.append(base)
    for part in re.split(r"[\s_/]+", base):
        part = part.strip()
        if len(part) >= 3 and part not in KEYWORD_BLOCKLIST and part not in NOISE_WORDS:
            words.append(part)
    for item in extra or []:
        kw = item.strip().lower()
        if len(kw) >= 3 and kw not in KEYWORD_BLOCKLIST and kw not in words:
            words.append(kw)
    return words[:8]


def _is_noise(name: str) -> bool:
    lower = name.lower().strip()
    if len(lower) < 3 or len(lower) > 80:
        return True
    if lower in NOISE_WORDS or lower in KEYWORD_BLOCKLIST:
        return True
    if lower.isdigit():
        return True
    if re.fullmatch(r"[\W\d_]+", lower):
        return True
    return False


def _parse_title_vendor(title: str) -> tuple[str, list[str], str]:
    """Extract vendor/product from forum or Reddit titles."""
    title = _normalize_company(title)
    if not title or _is_noise(title):
        return "", [], "low"

    match = BRACKET_RE.match(title)
    if match:
        company = _normalize_company(match.group(1))
        if company and not _is_noise(company):
            return company, _keywords_for(company), "medium"

    parts = TITLE_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) == 2:
        left, right = _normalize_company(parts[0]), _normalize_company(parts[1])
        if left and not _is_noise(left):
            kws = _keywords_for(left, [right] if right else None)
            return left, kws, "medium"

    if not _is_noise(title):
        return title, _keywords_for(title), "low"
    return "", [], "low"


def _extract_from_collector(
    parsed: _TextCollector,
    *,
    url: str,
    source_label: str,
    default_category: str,
    known: set[str],
) -> list[HarvestCandidate]:
    out: list[HarvestCandidate] = []
    seen: set[str] = set()

    def add_candidate(
        company: str,
        keywords: list[str],
        confidence: str,
        notes: str,
    ) -> None:
        company = _normalize_company(company)
        if not company or _is_noise(company):
            return
        key = company.lower()
        if key in seen:
            return
        seen.add(key)
        kws = keywords or _keywords_for(company)
        if not kws:
            return
        already = key in known or any(k in known for k in kws)
        out.append(
            HarvestCandidate(
                harvest_id=uuid.uuid4().hex[:12],
                company=company,
                keywords=kws,
                category=default_category,
                source_url=url,
                source_label=source_label,
                confidence=confidence,
                notes=notes,
                already_known=already,
                created=_now_iso(),
            )
        )

    host = urlparse(url).netloc.lower()

    if "fandom.com" in host or "wikia.com" in host:
        for cell in parsed.table_cells + parsed.list_items + parsed.headings:
            cell = _normalize_company(cell)
            if _is_noise(cell):
                continue
            if re.search(r"sound ideas|hollywood edge|sounddogs|library|sfx|foley", cell, re.I):
                add_candidate(cell, _keywords_for(cell), "high", "wiki table/list entry")
            elif len(cell.split()) <= 6:
                add_candidate(cell, _keywords_for(cell), "medium", "wiki entry")

    elif "sounddogs.com" in host:
        for text, _href in parsed.links:
            text = _normalize_company(text)
            if text and not _is_noise(text) and len(text) > 4:
                add_candidate(text, _keywords_for(text, ["sounddogs"]), "high", "sounddogs nav/link")
        add_candidate("Sounddogs", ["sounddogs", "rob nokes"], "high", "sounddogs root")

    elif "reddit.com" in host:
        if parsed.title:
            sub = parsed.title.split(":")[0].replace("reddit", "").strip()
            if sub and not _is_noise(sub):
                add_candidate(sub, _keywords_for(sub), "low", "subreddit title")
        for text, _href in parsed.links[:80]:
            company, kws, conf = _parse_title_vendor(text)
            if company:
                add_candidate(company, kws, conf, "reddit link text")

    elif "kvraudio.com" in host:
        for text, href in parsed.links:
            if "viewtopic" not in href and "viewforum" not in href:
                continue
            company, kws, conf = _parse_title_vendor(text)
            if company:
                add_candidate(company, kws, conf, "kvr thread title")

    elif "vi-control.net" in host:
        for text, href in parsed.links[:120]:
            company, kws, conf = _parse_title_vendor(text)
            if company:
                add_candidate(company, kws, conf, "vi-control thread/link")
        if parsed.title:
            company, kws, conf = _parse_title_vendor(parsed.title)
            if company:
                add_candidate(company, kws, conf, "vi-control title")

    elif "gearspace.com" in host or "gearslutz.com" in host:
        for text, _href in parsed.links[:100]:
            company, kws, conf = _parse_title_vendor(text)
            if company:
                add_candidate(company, kws, conf, "gearspace thread")

    else:
        for text, _href in parsed.links[:60]:
            company, kws, conf = _parse_title_vendor(text)
            if company:
                add_candidate(company, kws, conf, "generic link")
        for heading in parsed.headings[:20]:
            company, kws, conf = _parse_title_vendor(heading)
            if company:
                add_candidate(company, kws, conf, "generic heading")

    return out


def _source_label(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "kvraudio" in host:
        return "KVR Audio"
    if "vi-control" in host:
        return "vi-control"
    if "reddit" in host:
        path = urlparse(url).path.strip("/").split("/")
        return f"Reddit r/{path[1]}" if len(path) >= 2 and path[0] == "r" else "Reddit"
    if "fandom.com" in host:
        return "Fandom Wiki"
    if "sounddogs" in host:
        return "Sounddogs"
    if "gearspace" in host or "gearslutz" in host:
        return "Gearspace"
    if "soundonsound" in host:
        return "Sound On Sound"
    return host or "web"


def harvest_url(
    url: str,
    *,
    default_category: str = "User_Added",
    known: set[str] | None = None,
) -> tuple[list[HarvestCandidate], HarvestResult]:
    known = known or _known_vendor_set()
    label = _source_label(url)
    try:
        html, fetch_ms = fetch_page(url)
        parsed = parse_html(html)
        candidates = _extract_from_collector(
            parsed,
            url=url,
            source_label=label,
            default_category=default_category,
            known=known,
        )
        return candidates, HarvestResult(
            url=url,
            source_label=label,
            ok=True,
            candidates_found=len(candidates),
            fetch_ms=fetch_ms,
        )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return [], HarvestResult(url=url, source_label=label, ok=False, error=str(exc))


def run_harvest(
    urls: list[str],
    *,
    default_category: str = "User_Added",
    include_known: bool = False,
) -> dict:
    from api.security import validate_harvest_urls

    urls = list(dict.fromkeys(validate_harvest_urls([url.strip() for url in urls if url.strip()])))
    known = _known_vendor_set()
    all_candidates: list[HarvestCandidate] = []
    results: list[HarvestResult] = []

    for index, url in enumerate(urls):
        if index > 0:
            time.sleep(FETCH_DELAY_S)
        found, result = harvest_url(url, default_category=default_category, known=known)
        results.append(result)
        for row in found:
            if row.already_known and not include_known:
                continue
            all_candidates.append(row)
    return _merge_harvest(urls, default_category, all_candidates, results)


@serialized_store(lambda: CANDIDATES_PATH)
def _merge_harvest(urls, default_category, all_candidates, results) -> dict:

    store = load_candidates()
    pending = {}
    reviewed = set()
    for saved in store.setdefault("candidates", []):
        key = saved["company"].strip().casefold()
        if saved.get("status") == "pending":
            pending.setdefault(key, saved)
        else:
            reviewed.update((key, u) for u in saved.get("sources", [saved["source_url"]]))
    added = 0
    for row in all_candidates:
        key = row.company.strip().casefold()
        if (key, row.source_url) in reviewed:
            continue
        if key in pending:
            existing = pending[key]
            sources = existing.setdefault("sources", [existing["source_url"]])
            if row.source_url not in sources:
                sources.append(row.source_url)
            continue
        saved = row.to_dict()
        saved["sources"] = [row.source_url]
        store["candidates"].append(saved)
        pending[key] = saved
        added += 1

    store["updated"] = _now_iso()
    store["last_run"] = {
        "urls": urls,
        "category": default_category,
        "results": [r.__dict__ for r in results],
        "added": added,
    }
    save_candidates(store)

    return {
        "ok": True,
        "added": added,
        "total_pending": sum(1 for c in store["candidates"] if c.get("status") == "pending"),
        "results": [r.__dict__ for r in results],
    }


def list_source_presets() -> list[dict[str, object]]:
    return HARVEST_SOURCE_PRESETS


def load_candidates() -> dict:
    if not CANDIDATES_PATH.is_file():
        return {"version": 1, "updated": "", "candidates": [], "last_run": None}
    return json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))


def save_candidates(data: dict) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    data["version"] = 1
    write_json(CANDIDATES_PATH, data)
    return CANDIDATES_PATH


def list_pending_candidates(*, include_known: bool = True) -> list[dict]:
    store = load_candidates()
    rows = [row for row in store.get("candidates", []) if row.get("status") == "pending"]
    if not include_known:
        rows = [row for row in rows if not row.get("already_known")]
    return sorted(rows, key=lambda r: (r.get("already_known", False), r.get("company", "")))


@serialized_store(lambda: CANDIDATES_PATH)
def approve_candidates(harvest_ids: list[str]) -> dict:
    store = load_candidates()
    approved: list[dict] = []
    for row in store.get("candidates", []):
        if row.get("harvest_id") not in harvest_ids or row.get("status") != "pending":
            continue
        vendor = add_user_vendor(
            row["company"],
            row.get("keywords") or [row["company"].lower()],
            category=row.get("category") or "User_Added",
        )
        row["status"] = "approved"
        approved.append(vendor.to_dict())
    store["updated"] = _now_iso()
    save_candidates(store)
    return {"ok": True, "approved": approved, "count": len(approved)}


@serialized_store(lambda: CANDIDATES_PATH)
def reject_candidates(harvest_ids: list[str]) -> dict:
    store = load_candidates()
    count = 0
    for row in store.get("candidates", []):
        if row.get("harvest_id") in harvest_ids and row.get("status") == "pending":
            row["status"] = "rejected"
            count += 1
    store["updated"] = _now_iso()
    save_candidates(store)
    return {"ok": True, "rejected": count}


def export_candidates_csv(*, include_known: bool = False, status: str = "pending") -> Path:
    """Write research inbox to CSV for offline review (does not touch vendor base)."""
    import csv

    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    out_path = FEEDBACK_DIR / f"Vendor_Research_Export_{stamp}.csv"
    store = load_candidates()
    rows = store.get("candidates", [])
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if not include_known:
        rows = [r for r in rows if not r.get("already_known")]
    fieldnames = [
        "company",
        "keywords",
        "category",
        "confidence",
        "source_label",
        "source_url",
        "already_known",
        "status",
        "notes",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "keywords": ", ".join(row.get("keywords") or []),
                }
            )
    return out_path


def run_preset(preset_id: str, *, include_known: bool = False) -> dict:
    preset = next((p for p in HARVEST_SOURCE_PRESETS if p["id"] == preset_id), None)
    if not preset:
        raise ValueError(f"Unknown preset: {preset_id}")
    urls = list(preset["urls"])  # type: ignore[arg-type]
    category = str(preset.get("default_category", "User_Added"))
    return run_harvest(urls, default_category=category, include_known=include_known)
