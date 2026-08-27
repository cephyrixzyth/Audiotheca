"""Acoustic near-dupe grouping via Chromaprint similarity (Sononym-style lane)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audiotheca.audio_fingerprint import AUDIO_EXTS, fingerprint_file
from reference_dedupe_engine import acoustic_fingerprint

DEFAULT_THRESHOLD = 0.85
MAX_PATHS = 500


def _decode_fingerprint(fp: str) -> list[int] | None:
    """Decode Chromaprint compressed fingerprint to int list when possible."""
    try:
        import acoustid  # type: ignore[import-untyped]

        decode = getattr(getattr(acoustid, "chromaprint", None), "decode_fingerprint", None)
        if decode is None:
            return None
        decoded, _version = decode(fp)
        if not decoded:
            return None
        return list(decoded)
    except Exception:  # noqa: BLE001
        return None


def fingerprint_similarity(a: str, b: str) -> float:
    """Return similarity in [0, 1]. Exact match = 1.0; else Hamming on decoded ints."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    left = _decode_fingerprint(a)
    right = _decode_fingerprint(b)
    if not left or not right:
        return 0.0
    n = min(len(left), len(right))
    if n == 0:
        return 0.0
    left = left[:n]
    right = right[:n]
    # Each chromaprint int is 32 bits; count matching bits.
    matching_bits = 0
    total_bits = n * 32
    for x, y in zip(left, right):
        xor = (int(x) ^ int(y)) & 0xFFFFFFFF
        matching_bits += 32 - bin(xor).count("1")
    return matching_bits / total_bits if total_bits else 0.0


def _fingerprint_row(path: Path) -> dict[str, Any]:
    chromaprint = fingerprint_file(path)
    if chromaprint.get("ok") and chromaprint.get("fingerprint"):
        return {
            "path": str(path),
            "ok": True,
            "fingerprint": str(chromaprint["fingerprint"]),
            "duration": chromaprint.get("duration"),
            "backend": chromaprint.get("backend", "chromaprint"),
            "ext": path.suffix.lower(),
            "mode": "chromaprint",
        }

    heuristic = acoustic_fingerprint(path)
    return {
        "path": str(path),
        "ok": bool(heuristic.get("fingerprint")),
        "fingerprint": heuristic.get("fingerprint"),
        "duration": heuristic.get("duration_s"),
        "backend": "hash_duration_heuristic",
        "ext": path.suffix.lower(),
        "mode": "heuristic",
        "error": chromaprint.get("error"),
    }


def find_near_duplicates(
    paths: list[str | Path],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    max_paths: int = MAX_PATHS,
) -> dict[str, Any]:
    """
    Group paths that are acoustically near-duplicates (cross-format friendly).

    Prefer Chromaprint when available; fall back to hash/duration heuristic exact groups.
    """
    cleaned: list[Path] = []
    for raw in paths[: max(1, max_paths)]:
        target = Path(raw)
        if target.is_file() and target.suffix.lower() in AUDIO_EXTS | {".wave", ".ncw"}:
            cleaned.append(target)

    rows = [_fingerprint_row(path) for path in cleaned]
    usable = [row for row in rows if row.get("ok") and row.get("fingerprint")]

    # Exact fingerprint buckets (chromaprint or heuristic).
    by_fp: dict[str, list[dict[str, Any]]] = {}
    for row in usable:
        by_fp.setdefault(str(row["fingerprint"]), []).append(row)

    groups: list[dict[str, Any]] = []
    seen_pairs: set[frozenset[str]] = set()

    for fp, members in by_fp.items():
        if len(members) < 2:
            continue
        paths_out = [str(m["path"]) for m in members]
        exts = sorted({str(m["ext"]) for m in members})
        groups.append(
            {
                "kind": "exact",
                "similarity": 1.0,
                "fingerprint": fp,
                "paths": paths_out,
                "count": len(paths_out),
                "cross_format": len(exts) > 1,
                "exts": exts,
                "mode": members[0].get("mode"),
                "backend": members[0].get("backend"),
            }
        )
        seen_pairs.add(frozenset(paths_out))

    # Near matches across distinct chromaprint strings (pairwise).
    chroma_rows = [row for row in usable if row.get("mode") == "chromaprint"]
    for i, left in enumerate(chroma_rows):
        for right in chroma_rows[i + 1 :]:
            if left["fingerprint"] == right["fingerprint"]:
                continue
            score = fingerprint_similarity(str(left["fingerprint"]), str(right["fingerprint"]))
            if score < threshold:
                continue
            pair = frozenset({str(left["path"]), str(right["path"])})
            if pair in seen_pairs:
                continue
            # Skip if both already in a larger exact group together.
            seen_pairs.add(pair)
            paths_out = [str(left["path"]), str(right["path"])]
            exts = sorted({str(left["ext"]), str(right["ext"])})
            groups.append(
                {
                    "kind": "near",
                    "similarity": round(score, 4),
                    "fingerprint": None,
                    "paths": paths_out,
                    "count": 2,
                    "cross_format": len(exts) > 1,
                    "exts": exts,
                    "mode": "chromaprint",
                    "backend": left.get("backend"),
                }
            )

    groups.sort(key=lambda g: (-float(g.get("similarity") or 0), -int(g.get("count") or 0)))
    return {
        "scanned": len(cleaned),
        "fingerprinted": len(usable),
        "threshold": threshold,
        "group_count": len(groups),
        "groups": groups,
        "errors": [
            {"path": row["path"], "error": row.get("error")}
            for row in rows
            if not row.get("ok") and row.get("error")
        ][:50],
        "mode": "acoustic_near_dupe",
    }
