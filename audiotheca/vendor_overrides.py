"""User-added vendor keywords — merged into engine routing at scan time."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from api.paths import report_dir
from audiotheca.local_storage import serialized_store, write_json
from pathlib import Path

from audiotheca.config import KEYWORD_BLOCKLIST
from vendor_db import VENDOR_DATABASE

FEEDBACK_DIR = report_dir() / "feedback"
OVERRIDES_PATH = FEEDBACK_DIR / "vendor_overrides.json"
BUCKET_OVERRIDES_PATH = FEEDBACK_DIR / "bucket_overrides.json"


@dataclass
class UserVendor:
    company: str
    keywords: list[str] = field(default_factory=list)
    category: str = "User_Added"
    created: str = ""

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "keywords": self.keywords,
            "category": self.category,
            "created": self.created,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_user_vendors() -> list[UserVendor]:
    if not OVERRIDES_PATH.is_file():
        return _vendors_from_investigation_store()
    data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    rows = data.get("vendors", [])
    return [UserVendor(**row) for row in rows]


def _vendors_from_investigation_store() -> list[UserVendor]:
    try:
        import investigation_feedback as inv

        store = inv.load_store()
        return [
            UserVendor(
                company=row.company,
                keywords=row.keywords,
                category=row.category,
                created=row.created,
            )
            for row in store.vendor_additions
        ]
    except ImportError:
        return []


def save_user_vendors(vendors: list[UserVendor]) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated": _now_iso(),
        "vendors": [row.to_dict() for row in vendors],
    }
    write_json(OVERRIDES_PATH, payload)
    return OVERRIDES_PATH


@serialized_store(lambda: OVERRIDES_PATH)
def add_user_vendor(
    company: str,
    keywords: list[str],
    *,
    category: str = "User_Added",
) -> UserVendor:
    company = company.strip()
    kw = [k.strip().lower() for k in keywords if k.strip()]
    if not kw:
        kw = [company.lower()]
    vendors = load_user_vendors()
    row = UserVendor(company=company, keywords=kw, category=category, created=_now_iso())
    vendors = [v for v in vendors if v.company.lower() != company.lower()]
    vendors.append(row)
    save_user_vendors(vendors)
    return row


def sync_bucket_overrides(custom_buckets: dict[str, str]) -> Path:
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "updated": _now_iso(), "custom_buckets": custom_buckets}
    write_json(BUCKET_OVERRIDES_PATH, payload)
    return BUCKET_OVERRIDES_PATH


def all_known_vendors() -> list[str]:
    names: set[str] = set()
    for group in VENDOR_DATABASE.values():
        names.update(group.keys())
    for row in load_user_vendors():
        names.add(row.company)
    return sorted(names)


def match_keyword(keyword: str, sample: str) -> dict:
    """Return whether a keyword would match sample text (same rules as engine routes)."""
    kw = keyword.strip().lower()
    sample_lower = sample.lower()
    if len(kw) < 3:
        return {"keyword": kw, "matches": False, "reason": "keyword too short (min 3)"}
    if kw in KEYWORD_BLOCKLIST:
        return {"keyword": kw, "matches": False, "reason": "keyword is blocklisted"}

    escaped = re.escape(kw)
    if not kw[-1].isalnum():
        pattern = re.compile(r"\b" + escaped)
    elif len(kw) >= 6:
        pattern = re.compile(r"\b" + escaped + r"(?:\b|s\b)")
    else:
        pattern = re.compile(r"\b" + escaped + r"\b")

    match = pattern.search(sample_lower)
    return {
        "keyword": kw,
        "matches": match is not None,
        "match_span": match.group(0) if match else None,
        "reason": "matched" if match else "no match",
    }


def compile_user_routes() -> list[tuple[str, re.Pattern[str], bool]]:
    """Extra vendor routes from user overrides (strong priority)."""
    staged: list[tuple[int, int, str, re.Pattern[str]]] = []
    from audiotheca.extensions import vendor_rows as extension_vendor_rows

    for row in [*load_user_vendors(), *extension_vendor_rows()]:
        for position, keyword in enumerate(row.keywords):
            kw = keyword.strip().lower()
            if len(kw) < 3 or kw in KEYWORD_BLOCKLIST:
                continue
            strong = position == 0 or " " in kw or len(kw) >= 8
            escaped = re.escape(kw)
            if not kw[-1].isalnum():
                pattern = re.compile(r"\b" + escaped)
            elif len(kw) >= 6:
                pattern = re.compile(r"\b" + escaped + r"(?:\b|s\b)")
            else:
                pattern = re.compile(r"\b" + escaped + r"\b")
            staged.append((0 if strong else 1, -len(kw), row.company, pattern))
    staged.sort(key=lambda entry: (entry[0], entry[1]))
    return [(vendor, pattern, rank == 0) for rank, _, vendor, pattern in staged]
