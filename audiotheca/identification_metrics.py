"""Run-level identification / routing metrics for dashboard and compare views."""

from __future__ import annotations

import csv
from pathlib import Path

from audiotheca.config import REPORT_DIR


def _report(stamp: str, prefix: str, suffix: str = ".csv") -> Path:
    return REPORT_DIR / f"{prefix}_{stamp}{suffix}"


def compute_run_metrics(stamp: str) -> dict[str, object]:
    plan_path = _report(stamp, "Restructure_Plan")
    inv_path = _report(stamp, "Investigation_Breakdown")

    ready = needs_review = 0
    id_methods_ready: dict[str, int] = {}
    id_methods_inv: dict[str, int] = {}
    identified_routes = 0

    if plan_path.is_file():
        with plan_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                status = row.get("Status", "")
                method = row.get("ID Method", "") or "NONE"
                if status == "READY":
                    ready += 1
                    id_methods_ready[method] = id_methods_ready.get(method, 0) + 1
                elif status == "NEEDS REVIEW":
                    needs_review += 1
                if method != "NONE":
                    identified_routes += 1

    buckets: dict[str, int] = {}
    if inv_path.is_file():
        with inv_path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                bucket = row.get("Investigation Bucket", "")
                buckets[bucket] = buckets.get(bucket, 0) + 1
                method = row.get("ID Method", "") or "NONE"
                id_methods_inv[method] = id_methods_inv.get(method, 0) + 1

    routes = ready + needs_review
    inv_total = sum(buckets.values())

    return {
        "stamp": stamp,
        "routes_planned": routes,
        "ready_count": ready,
        "needs_review_count": needs_review,
        "investigation_count": inv_total,
        "route_ready_pct": round(100 * ready / routes, 1) if routes else 0.0,
        "identification_pct": round(100 * identified_routes / routes, 1) if routes else 0.0,
        "one_action_pct": round(
            100 * buckets.get("_unverified_vendor", 0) / inv_total, 1
        )
        if inv_total
        else 0.0,
        "investigation_buckets": buckets,
        "id_methods_ready": id_methods_ready,
        "id_methods_investigation": id_methods_inv,
    }


def compare_run_metrics(stamp_a: str, stamp_b: str) -> dict[str, object]:
    a = compute_run_metrics(stamp_a)
    b = compute_run_metrics(stamp_b)

    def delta(key: str) -> float | int:
        av = a.get(key, 0)
        bv = b.get(key, 0)
        if isinstance(av, (int, float)) and isinstance(bv, (int, float)):
            return round(float(bv) - float(av), 1) if isinstance(av, float) else int(bv) - int(av)
        return 0

    bucket_delta: dict[str, int] = {}
    all_buckets = set(a.get("investigation_buckets", {})) | set(b.get("investigation_buckets", {}))
    for bucket in all_buckets:
        old = (a.get("investigation_buckets") or {}).get(bucket, 0)
        new = (b.get("investigation_buckets") or {}).get(bucket, 0)
        diff = new - old
        if diff:
            bucket_delta[bucket] = diff

    return {
        "stamp_a": stamp_a,
        "stamp_b": stamp_b,
        "metrics_a": a,
        "metrics_b": b,
        "delta": {
            "route_ready_pct": delta("route_ready_pct"),
            "identification_pct": delta("identification_pct"),
            "ready_count": delta("ready_count"),
            "investigation_count": delta("investigation_count"),
            "needs_review_count": delta("needs_review_count"),
        },
        "bucket_delta": bucket_delta,
    }
