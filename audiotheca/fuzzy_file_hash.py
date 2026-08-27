"""Fuzzy file similarity for installer/pack near-dupes (ssdeep / TLSH / rolling fallback)."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from audiotheca.dedupe_blocking import group_by_size_bucket, size_bucket

DEFAULT_THRESHOLD = 70  # ssdeep/TLSH-style score scale 0–100
MAX_COMPARE_BYTES = 8 * 1024 * 1024
CHUNK = 64 * 1024


def _ssdeep_hash(path: Path) -> str | None:
    try:
        import ssdeep  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        return str(ssdeep.hash_from_file(str(path)))
    except Exception:  # noqa: BLE001
        return None


def _tlsh_hash(path: Path) -> str | None:
    try:
        import tlsh  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        data = path.read_bytes()
        if len(data) < 50:
            return None
        digest = tlsh.hash(data)
        return digest if digest and digest != "TNULL" else None
    except Exception:  # noqa: BLE001
        return None


def _rolling_digest(path: Path) -> str:
    """Stdlib CDC-ish fingerprint: rolling window hashes concatenated."""
    hasher = hashlib.sha1()
    window = bytearray()
    try:
        with path.open("rb") as handle:
            remaining = MAX_COMPARE_BYTES
            while remaining > 0:
                block = handle.read(min(CHUNK, remaining))
                if not block:
                    break
                remaining -= len(block)
                window.extend(block)
                # Emit a feature every ~4KB boundary for stability.
                while len(window) >= 4096:
                    piece = bytes(window[:4096])
                    del window[:4096]
                    feature = hashlib.blake2b(piece, digest_size=4).digest()
                    hasher.update(feature)
            if window:
                hasher.update(hashlib.blake2b(bytes(window), digest_size=4).digest())
    except OSError:
        return ""
    return hasher.hexdigest()


def fuzzy_hash(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        return {"ok": False, "error": "not a file", "path": str(target)}
    try:
        size = target.stat().st_size
    except OSError as exc:
        return {"ok": False, "error": str(exc), "path": str(target)}

    ss = _ssdeep_hash(target)
    tl = _tlsh_hash(target)
    rolling = _rolling_digest(target)
    engine = "ssdeep" if ss else "tlsh" if tl else "rolling"
    digest = ss or tl or rolling
    return {
        "ok": bool(digest),
        "path": str(target),
        "size": size,
        "size_bucket": size_bucket(size),
        "engine": engine,
        "digest": digest,
        "ssdeep": ss,
        "tlsh": tl,
        "rolling": rolling or None,
    }


def fuzzy_compare(a: str, b: str, *, engine: str | None = None) -> dict[str, Any]:
    """Compare two digests; score 0–100 (higher = more similar)."""
    left, right = (a or "").strip(), (b or "").strip()
    if not left or not right:
        return {"score": 0, "engine": engine or "none", "match": False}
    if left == right:
        return {"score": 100, "engine": engine or "exact", "match": True}

    if engine == "ssdeep" or (not engine and left[:1].isdigit()):
        try:
            import ssdeep  # type: ignore[import-untyped]

            score = int(ssdeep.compare(left, right))
            return {"score": score, "engine": "ssdeep", "match": score >= DEFAULT_THRESHOLD}
        except Exception:  # noqa: BLE001
            pass

    if engine == "tlsh" or left.startswith("T1") or right.startswith("T1"):
        try:
            import tlsh  # type: ignore[import-untyped]

            dist = int(tlsh.diff(left, right))
            # TLSH distance: 0 identical; map roughly into 0–100 similarity.
            score = max(0, 100 - dist)
            return {"score": score, "engine": "tlsh", "match": score >= DEFAULT_THRESHOLD, "distance": dist}
        except Exception:  # noqa: BLE001
            pass

    # Rolling: shared prefix length / total as crude similarity.
    n = min(len(left), len(right))
    shared = 0
    for i in range(n):
        if left[i] == right[i]:
            shared += 1
        else:
            break
    score = int(100 * shared / max(n, 1))
    # Also reward equal length + high character overlap.
    if left and right and abs(len(left) - len(right)) <= 2:
        overlap = sum(1 for x, y in zip(left, right) if x == y)
        score = max(score, int(100 * overlap / max(len(left), len(right))))
    return {"score": score, "engine": engine or "rolling", "match": score >= DEFAULT_THRESHOLD}


def find_fuzzy_blocked_pairs(
    items: list[dict],
    *,
    min_size_bytes: int = 256 * 1024,
    threshold: int = DEFAULT_THRESHOLD,
    max_per_bucket: int = 40,
) -> list[dict]:
    """Within size buckets, pair items with high fuzzy similarity but different exact content."""
    buckets = group_by_size_bucket(items)
    groups: list[dict] = []

    for bucket_id, bucket_items in buckets.items():
        if len(bucket_items) < 2:
            continue
        candidates = [
            item
            for item in bucket_items
            if int(item.get("size") or 0) >= min_size_bytes and item.get("path")
        ][:max_per_bucket]
        if len(candidates) < 2:
            continue

        hashed: list[tuple[dict, dict[str, Any]]] = []
        for item in candidates:
            digest = fuzzy_hash(str(item["path"]))
            if digest.get("ok") and digest.get("digest"):
                hashed.append((item, digest))

        used: set[str] = set()
        for i, (left_item, left_hash) in enumerate(hashed):
            cluster = [left_item]
            for right_item, right_hash in hashed[i + 1 :]:
                key = frozenset({str(left_item["path"]), str(right_item["path"])})
                if str(key) in used:
                    continue
                # Skip if identical rolling digest already grouped as exact elsewhere.
                if left_hash["digest"] == right_hash["digest"]:
                    score = 100
                else:
                    cmp = fuzzy_compare(
                        str(left_hash["digest"]),
                        str(right_hash["digest"]),
                        engine=str(left_hash.get("engine")),
                    )
                    score = int(cmp["score"])
                if score < threshold:
                    continue
                cluster.append(right_item)
                used.add(str(key))
            if len(cluster) < 2:
                continue
            keep = max(cluster, key=lambda entry: (entry.get("version_key", ""), int(entry.get("size") or 0)))
            digest_preview = hashed[i][1]["digest"][:16]
            groups.append(
                {
                    "dedup_key": f"fuzzy|{bucket_id}|{digest_preview}",
                    "confidence": "MEDIUM",
                    "group_kind": "FUZZY_PACK",
                    "name_similarity": 0,
                    "size_ratio": 1.0,
                    "same_version": False,
                    "content_check": "FUZZY",
                    "fuzzy_score": threshold,
                    "fuzzy_engine": hashed[i][1].get("engine"),
                    "recommended_keep": keep,
                    "items": sorted(cluster, key=lambda entry: str(entry.get("original_name") or entry.get("path"))),
                    "paths": [str(item.get("path")) for item in cluster],
                    "count": len(cluster),
                    "action": "REVIEW — fuzzy similar packs/installers in same size bucket",
                }
            )
    return groups


def find_fuzzy_duplicates(paths: list[str | Path], *, threshold: int = DEFAULT_THRESHOLD) -> dict[str, Any]:
    items = []
    for raw in paths:
        target = Path(raw)
        if not target.is_file():
            continue
        try:
            size = target.stat().st_size
        except OSError:
            continue
        items.append({"path": str(target), "size": size, "original_name": target.name})
    groups = find_fuzzy_blocked_pairs(items, threshold=threshold, min_size_bytes=1024)
    return {
        "scanned": len(items),
        "group_count": len(groups),
        "groups": groups,
        "threshold": threshold,
        "mode": "fuzzy_pack",
    }
