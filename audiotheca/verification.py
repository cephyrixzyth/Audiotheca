"""Phase 3.5 — post-plan verification: quality scorecard + QA findings.

Runs after the restructure plan is computed and answers "how close is this
run to 100% identified / deduped / routed, and what exactly is holding it
back?" Produces:

- a scorecard dict (rates per pillar) written to Quality_Scorecard JSON
- findings rows (one actionable row each) written to Verification_Findings CSV
"""

from __future__ import annotations

import re
from collections import defaultdict

from audiotheca.helpers import _squash

# Leading tokens that never indicate a vendor.
GENERIC_LEAD_TOKENS = frozenset(
    {
        "the", "new", "best", "free", "full", "final", "and", "for", "vol",
        "sample", "samples", "loop", "loops", "drum", "drums", "kit", "kits",
        "pack", "packs", "preset", "presets", "sound", "sounds", "midi",
        "vst", "vst3", "plugin", "plugins", "audio", "music", "studio",
        "update", "win", "mac", "windows", "osx", "x64", "setup",
    }
)

MIN_CLUSTER_SIZE = 3


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 100.0


def confidence_category(id_confidence: str = "UNKNOWN", id_method: str = "") -> dict[str, object]:
    """CONF-CAT: map identification confidence to review tier badges."""
    conf = str(id_confidence or "UNKNOWN").upper()
    method = str(id_method or "").upper()
    if conf == "CONFIRMED":
        tier, tone, needs_review = "verified", "accent", False
    elif conf == "TENTATIVE":
        tier, tone, needs_review = "pending", "warning", True
    else:
        tier, tone, needs_review = "unknown", "danger", True
    return {
        "tier": tier,
        "tone": tone,
        "badge": conf,
        "id_confidence": conf,
        "id_method": method,
        "needs_review": needs_review,
    }


def build_scorecard(
    all_items: list[dict],
    *,
    duplicate_groups: list[dict],
    investigation_plan: list[dict],
    restructure_plan: list[dict],
    build_dedup_key,
) -> dict:
    """Coverage rates for the four pillars: identify, dedupe, route, investigate."""
    total = len(all_items)
    confirmed = sum(1 for i in all_items if i.get("id_confidence") == "CONFIRMED")
    tentative = sum(1 for i in all_items if i.get("id_confidence") == "TENTATIVE")
    unknown = total - confirmed - tentative

    dedupe_eligible = sum(1 for i in all_items if build_dedup_key(i))
    ready = sum(1 for e in restructure_plan if e.get("status") == "READY")
    needs_review = sum(1 for e in restructure_plan if e.get("status") != "READY")

    bucket_counts: dict[str, int] = defaultdict(int)
    for entry in investigation_plan:
        bucket_counts[entry.get("bucket", "?")] += 1

    return {
        "total_items": total,
        "identified_confirmed": confirmed,
        "identified_tentative": tentative,
        "identified_unknown": unknown,
        "identification_rate_pct": _pct(confirmed + tentative, total),
        "confirmed_rate_pct": _pct(confirmed, total),
        "dedupe_eligible": dedupe_eligible,
        "dedupe_eligible_pct": _pct(dedupe_eligible, total),
        "duplicate_groups": len(duplicate_groups),
        "duplicate_groups_high": sum(
            1 for g in duplicate_groups if g.get("confidence") == "HIGH"
        ),
        "routes_ready": ready,
        "routes_needing_review": needs_review,
        "route_ready_pct": _pct(ready, len(restructure_plan)),
        "investigation_items": len(investigation_plan),
        "investigation_pct": _pct(len(investigation_plan), total),
        "investigation_buckets": dict(sorted(bucket_counts.items())),
    }


def _lead_token(name: str) -> str:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9&']+", name)
    return tokens[0].lower() if tokens else ""


def find_vendor_candidates(all_items: list[dict]) -> list[dict]:
    """Cluster unknown items by leading name token → vendor candidates.

    Three or more unknown items starting with the same non-generic token is a
    strong hint that token is an unlisted vendor. Surfacing these lets the
    user add one keyword and identify the whole cluster on the next run.
    """
    clusters: dict[str, list[dict]] = defaultdict(list)
    for item in all_items:
        if item.get("company"):
            continue
        token = _lead_token(item["original_name"])
        if len(token) >= 4 and token not in GENERIC_LEAD_TOKENS:
            clusters[token].append(item)

    findings: list[dict] = []
    for token, items in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        if len(items) < MIN_CLUSTER_SIZE:
            continue
        sample = "; ".join(i["original_name"][:40] for i in items[:3])
        findings.append(
            {
                "check": "VENDOR_CANDIDATE",
                "severity": "SUGGESTION",
                "subject": token,
                "path": str(items[0]["path"]),
                "detail": f"{len(items)} unknown items start with '{token}' (e.g. {sample})",
                "suggestion": f"Add '{token}' as a vendor keyword to identify {len(items)} items",
            }
        )
    return findings


def find_destination_collisions(restructure_plan: list[dict]) -> list[dict]:
    """Two different sources planned into the same destination folder."""
    by_dest: dict[str, list[dict]] = defaultdict(list)
    for entry in restructure_plan:
        if entry.get("investigation_bucket"):
            continue
        dest = (entry.get("destination") or "").lower()
        if dest:
            by_dest[dest].append(entry)

    findings: list[dict] = []
    for dest, entries in by_dest.items():
        if len(entries) < 2:
            continue
        names = {e["original_name"] for e in entries}
        if len(names) < 2:
            continue  # same item listed twice is not a collision
        findings.append(
            {
                "check": "DEST_COLLISION",
                "severity": "WARNING",
                "subject": entries[0].get("destination", ""),
                "path": entries[0].get("current_path", ""),
                "detail": f"{len(entries)} different items route to the same destination: "
                + "; ".join(sorted(names)[:4]),
                "suggestion": "Review destinations — merging distinct products loses separation",
            }
        )
    return findings


def find_unverified_db_vendors(all_items: list[dict], vendor_aliases: dict[str, set[str]]) -> list[dict]:
    """Confirmed-vendor names that don't exist in the vendor database.

    These come from PE headers, NFO scrapes, or overrides; adding them to the
    DB upgrades every future match to a first-class keyword route.
    """
    known = {_squash(v) for v in vendor_aliases}
    by_vendor: dict[str, int] = defaultdict(int)
    sample_path: dict[str, str] = {}
    for item in all_items:
        company = item.get("company")
        if not company or item.get("id_confidence") != "CONFIRMED":
            continue
        if _squash(company) in known:
            continue
        by_vendor[company] += 1
        sample_path.setdefault(company, str(item["path"]))

    return [
        {
            "check": "VENDOR_NOT_IN_DB",
            "severity": "SUGGESTION",
            "subject": vendor,
            "path": sample_path[vendor],
            "detail": f"'{vendor}' confirmed on {count} item(s) but has no vendor DB entry",
            "suggestion": "Add to vendor DB so name-based matching works next run",
        }
        for vendor, count in sorted(by_vendor.items(), key=lambda kv: -kv[1])
    ]


def find_suspicious_keeps(duplicate_groups: list[dict]) -> list[dict]:
    """Duplicate groups where the recommended keep is much smaller than a
    discarded copy — usually means the version ordering picked a stub."""
    findings: list[dict] = []
    for group in duplicate_groups:
        keep = group.get("recommended_keep")
        items = group.get("items") or []
        if not keep or len(items) < 2:
            continue
        largest = max(items, key=lambda i: i.get("size", 0))
        keep_size = keep.get("size", 0)
        if largest.get("size", 0) > 0 and keep_size < largest["size"] * 0.5:
            findings.append(
                {
                    "check": "SUSPICIOUS_KEEP",
                    "severity": "WARNING",
                    "subject": group.get("dedup_key", ""),
                    "path": str(keep.get("path", "")),
                    "detail": (
                        f"Recommended keep '{keep.get('original_name', '')}' is "
                        f"{round(keep_size / (1024 * 1024), 1)} MB but "
                        f"'{largest.get('original_name', '')}' is "
                        f"{round(largest['size'] / (1024 * 1024), 1)} MB"
                    ),
                    "suggestion": "Verify the keeper — newer version may be an incomplete download",
                }
            )
    return findings


def run_verification(
    all_items: list[dict],
    *,
    duplicate_groups: list[dict],
    investigation_plan: list[dict],
    restructure_plan: list[dict],
    vendor_aliases: dict[str, set[str]],
    build_dedup_key,
) -> tuple[dict, list[dict]]:
    """Full verification pass. Returns (scorecard, findings)."""
    scorecard = build_scorecard(
        all_items,
        duplicate_groups=duplicate_groups,
        investigation_plan=investigation_plan,
        restructure_plan=restructure_plan,
        build_dedup_key=build_dedup_key,
    )
    findings: list[dict] = []
    findings.extend(find_vendor_candidates(all_items))
    findings.extend(find_unverified_db_vendors(all_items, vendor_aliases))
    findings.extend(find_destination_collisions(restructure_plan))
    findings.extend(find_suspicious_keeps(duplicate_groups))
    scorecard["findings_total"] = len(findings)
    scorecard["findings_warnings"] = sum(1 for f in findings if f["severity"] == "WARNING")
    scorecard["findings_suggestions"] = sum(1 for f in findings if f["severity"] == "SUGGESTION")
    return scorecard, findings
