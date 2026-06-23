"""
Extract audiotheca/engine.py methods into mixin modules (maintainer tool).

Run from repo root:  python scripts/extract_engine_mixins.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "audiotheca" / "engine.py"

HEADER = '''\
"""{title} mixin for DeduplicationEngine."""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import shutil
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from archive_peek import (
    find_7z,
    normalize_inferred_product,
    peek_scene_folders,
    peek_sibling_groups,
    scene_rename_blocked,
    sibling_groups_from_coexistence,
    write_peek_csv,
)
from duplicate_feedback import export_engine_hints, is_group_rejected, load_feedback_store
from investigation_feedback import (
    apply_hints_to_item,
    export_engine_hints as export_investigation_hints,
    get_bucket_override,
    load_store as load_investigation_store,
    merged_bucket_map,
)
from progress import PhaseProgress, tqdm_bar
from vendor_db import VENDOR_DATABASE

from audiotheca.config import *  # noqa: F403
from audiotheca.helpers import _archive_stem, _limit_walk, _squash, _walk_depth


class {class_name}Mixin:
'''

# 1-indexed inclusive line ranges (method bodies only)
RANGES: dict[str, list[tuple[int, int]]] = {
    "identify": [(239, 845)],
    "scan": [(306, 527), (1898, 1969)],
    "dedupe": [(846, 1075)],
    "routing": [(1076, 1292)],
    "reports": [(1293, 1708)],
    "archive": [(1709, 1897)],
}

KEEP_HEAD = (1, 238)
KEEP_TAIL = (1970, None)


def main() -> int:
    lines = ENGINE.read_text(encoding="utf-8").splitlines(keepends=True)

    for name, ranges in RANGES.items():
        class_name = name.capitalize()
        chunks: list[str] = []
        for start, end in ranges:
            chunks.extend(lines[start - 1 : end])
        body = "".join(chunks)
        out = ROOT / "audiotheca" / f"{name}.py"
        out.write_text(HEADER.format(title=class_name, class_name=class_name) + body, encoding="utf-8")
        print(f"Wrote {out.name} ({len(chunks)} lines)")

    head = lines[KEEP_HEAD[0] - 1 : KEEP_HEAD[1]]
    tail = lines[KEEP_TAIL[0] - 1 :]

    imports = [
        "from audiotheca.archive import ArchiveMixin\n",
        "from audiotheca.dedupe import DedupeMixin\n",
        "from audiotheca.identify import IdentifyMixin\n",
        "from audiotheca.reports import ReportsMixin\n",
        "from audiotheca.routing import RoutingMixin\n",
        "from audiotheca.scan import ScanMixin\n",
    ]
    insert_at = next(i for i, line in enumerate(head) if line.startswith("from audiotheca.helpers"))
    head = head[: insert_at + 1] + imports + head[insert_at + 1 :]

    for i, line in enumerate(head):
        if line.startswith("class DeduplicationEngine:"):
            head[i] = "class DeduplicationEngine(\n    ScanMixin,\n    IdentifyMixin,\n    DedupeMixin,\n    RoutingMixin,\n    ReportsMixin,\n    ArchiveMixin,\n):\n"
            break

    ENGINE.write_text("".join(head + tail), encoding="utf-8")
    print(f"Rewrote engine.py ({len(head) + len(tail)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
