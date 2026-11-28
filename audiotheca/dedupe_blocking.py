"""Size-bucket blocking for duplicate detection (dedupe.io style).

Only items in the same size bucket are compared pairwise, reducing false
positives from coincidentally similar names at very different file sizes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

# Logarithmic buckets: each bucket spans ~2x size range (base-2 log of bytes).
_SIZE_BUCKET_MIN_BYTES = 4096


def size_bucket(size_bytes: int) -> str:
    """Map a byte size to a dedupe blocking bucket id."""
    if size_bytes <= 0:
        return "empty"
    if size_bytes < _SIZE_BUCKET_MIN_BYTES:
        return "tiny"
    # Floor log2 gives stable buckets: 4KB→12, 1MB→20, 1GB→30, etc.
    bucket = int(math.floor(math.log2(max(size_bytes, _SIZE_BUCKET_MIN_BYTES))))
    return f"s{bucket}"


def group_by_size_bucket(items: Iterable[dict]) -> dict[str, list[dict]]:
    """Partition scan items into size buckets for blocking passes."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        groups[size_bucket(int(item.get("size") or 0))].append(item)
    return dict(groups)


def find_size_blocked_pairs(
    items: list[dict],
    *,
    min_size_bytes: int = 1024 * 1024,
    hash_fn,
) -> list[dict]:
    """Within each size bucket, group items sharing the same content hash.

    ``hash_fn`` receives a file path and returns a hex digest or None.
    Only buckets with 2+ members are hashed — cheap blocking before I/O.
    """
    buckets = group_by_size_bucket(items)
    groups: list[dict] = []

    for _bucket_id, bucket_items in buckets.items():
        if len(bucket_items) < 2:
            continue
        # Only files can be byte-identical; folders are matched by manifest
        # elsewhere. Sub-block on exact size so unique sizes are never hashed.
        by_exact: dict[int, list[dict]] = defaultdict(list)
        for item in bucket_items:
            size = int(item.get("size") or 0)
            if size < min_size_bytes or item.get("is_dir") or not item.get("path"):
                continue
            by_exact[size].append(item)
        by_hash: dict[str, list[dict]] = defaultdict(list)
        for same_size in by_exact.values():
            if len(same_size) < 2:
                continue
            for item in same_size:
                digest = hash_fn(item["path"])
                if digest:
                    by_hash[f"{digest}|{item['size']}"].append(item)
        for digest, matched in by_hash.items():
            if len(matched) < 2:
                continue
            # Identical bytes: prefer newest tag, then the most descriptive name.
            keep = max(
                matched,
                key=lambda entry: (entry.get("version_key", ""), len(entry.get("original_name") or "")),
            )
            groups.append(
                {
                    "dedup_key": f"sizeblock|{digest[:12]}|{matched[0]['size']}",
                    "confidence": "HIGH",
                    "group_kind": "SIZE_BLOCKED",
                    "name_similarity": 0,
                    "size_ratio": 1.0,
                    "same_version": True,
                    "content_check": "MATCH",
                    "recommended_keep": keep,
                    "items": sorted(matched, key=lambda entry: entry["original_name"]),
                    "action": "REVIEW — byte-identical items in same size bucket",
                }
            )
    return groups
