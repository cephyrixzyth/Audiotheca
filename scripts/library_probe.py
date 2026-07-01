"""Lightweight library probe — no engine, top-level + shallow stats for app feature ideas."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"Z:\_software\_audio")
SOFTWARE = Path(r"Z:\_software")
REPORT_DIR = Path(__file__).resolve().parent.parent / "dedupe_reports"
ARCHIVE = {".zip", ".rar", ".7z", ".iso", ".001", ".tar", ".gz"}
SCENE = re.compile(r"^[a-f0-9]{6,}$|^[A-Z0-9]{8,}$|^\d{5,8}$", re.I)


def probe_root(root: Path) -> dict:
    out: dict = {"root": str(root), "sections": {}, "errors": []}
    if not root.is_dir():
        out["errors"].append("root missing")
        return out

    bins = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
    out["section_count"] = len(bins)
    totals = Counter()

    for bin_p in bins:
        sec = bin_p.name
        row = {
            "dirs": 0,
            "files": 0,
            "archives": 0,
            "underscore": 0,
            "loose_archives": 0,
            "scene_hash_children": 0,
            "multi_subdir_folders": 0,
        }
        try:
            entries = list(bin_p.iterdir())
        except OSError as exc:
            row["error"] = str(exc)
            out["sections"][sec] = row
            continue

        for item in entries:
            if item.name.startswith("_"):
                row["underscore"] += 1
                totals["underscore"] += 1
                continue
            if item.is_file():
                row["files"] += 1
                totals["files"] += 1
                if item.suffix.lower() in ARCHIVE:
                    row["archives"] += 1
                    row["loose_archives"] += 1
                    totals["loose_archives"] += 1
                continue
            if not item.is_dir():
                continue
            row["dirs"] += 1
            totals["targets"] += 1
            try:
                subs = list(item.iterdir())
            except OSError:
                continue
            subdirs = [s for s in subs if s.is_dir()]
            if len(subdirs) > 2:
                row["multi_subdir_folders"] += 1
                totals["vendor_groupings"] += 1
            for sub in subdirs:
                if SCENE.match(sub.name.replace(".", "")):
                    row["scene_hash_children"] += 1
                    totals["scene_hash"] += 1

        out["sections"][sec] = row

    out["totals"] = dict(totals)
    out["underscore_samples"] = [
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.parent == root or (p.parent.parent == root and p.name.startswith("_"))
    ][:30]
    # fix underscore samples - only direct under sections
    samples: list[str] = []
    for sec, row in out["sections"].items():
        if row.get("underscore", 0) <= 0:
            continue
        try:
            for item in (root / sec).iterdir():
                if item.name.startswith("_"):
                    samples.append(str(item.relative_to(root)))
        except OSError:
            pass
    out["underscore_samples"] = samples[:25]
    return out


def analyze_reports(stamp: str) -> dict:
    base = REPORT_DIR
    out: dict = {"stamp": stamp}

    def load_csv(name: str) -> list[dict]:
        path = base / f"{name}_{stamp}.csv"
        if not path.is_file():
            return []
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    gaps = load_csv("Coverage_Gaps")
    nested = load_csv("Nested_Folder_Issues")
    coexist = load_csv("Archive_Coexistence")
    trunc = load_csv("Probe_Truncations")
    inv = load_csv("Investigation_Breakdown")

    gap_reasons = Counter(r.get("Reason", "") for r in gaps)
    nested_types = Counter(r.get("Issue Type", "") for r in nested)
    coexist_verdicts = Counter(r.get("Verdict", "") for r in coexist)

    inv_methods = Counter(r.get("ID Method", "") for r in inv if r.get("Investigation Bucket") == "_unverified_vendor")

    out["coverage_gaps"] = len(gaps)
    out["gap_reasons_top"] = gap_reasons.most_common(8)
    out["nested_issues"] = len(nested)
    out["nested_types_top"] = nested_types.most_common(8)
    out["coexistence_rows"] = len(coexist)
    out["coexistence_verdicts"] = coexist_verdicts.most_common(8)
    out["probe_truncations"] = len(trunc)
    out["unverified_id_methods"] = inv_methods.most_common(6)

    # Space recovery hints from coexistence
    redundant = [r for r in coexist if "redundant" in (r.get("Verdict") or "").lower()]
    out["redundant_archive_rows"] = len(redundant)

    return out


def software_siblings() -> list[str]:
    if not SOFTWARE.is_dir():
        return []
    try:
        return sorted(p.name for p in SOFTWARE.iterdir() if p.is_dir())
    except OSError:
        return []


def feature_ideas(probe: dict, reports: dict) -> list[dict]:
    ideas: list[dict] = []

    totals = probe.get("totals", {})
    if totals.get("underscore", 0) > 5:
        ideas.append(
            {
                "feature": "Underscore inventory panel",
                "why": f"{totals['underscore']} `_`-prefixed items are invisible to the engine",
                "samples": probe.get("underscore_samples", [])[:8],
            }
        )
    if totals.get("loose_archives", 0) > 20:
        ideas.append(
            {
                "feature": "Loose archive router",
                "why": f"{totals.get('loose_archives', 0)} top-level archives not inside product folders",
                "action": "Suggest vendor folder or explode-as-target toggle",
            }
        )
    if totals.get("vendor_groupings", 0) > 50:
        ideas.append(
            {
                "feature": "Vendor grouping map",
                "why": f"{totals.get('vendor_groupings', 0)} folders look like vendor bins with many subdirs",
                "action": "Visual tree: vendor → products, flag un-exploded children",
            }
        )
    if reports.get("coverage_gaps", 0) > 500:
        ideas.append(
            {
                "feature": "Coverage gap workflow",
                "why": f"{reports['coverage_gaps']} paths never scanned — top reasons: {reports.get('gap_reasons_top', [])[:3]}",
                "action": "One-click add to target list / rescan queue",
            }
        )
    if reports.get("redundant_archive_rows", 0) > 0:
        ideas.append(
            {
                "feature": "Space recovery dashboard",
                "why": f"{reports['redundant_archive_rows']} redundant archive coexistence rows",
                "action": "GB reclaim estimate + staged delete flow",
            }
        )
    if reports.get("probe_truncations", 0) > 30:
        ideas.append(
            {
                "feature": "Deep probe queue",
                "why": f"{reports['probe_truncations']} folders hit probe depth limit",
                "action": "Per-path deeper probe or invalidate cache",
            }
        )
    nested_top = reports.get("nested_types_top", [])
    if nested_top:
        ideas.append(
            {
                "feature": "Structure fixer",
                "why": f"Nested issue types: {nested_top[:4]}",
                "action": "Batch flatten scene wrappers / duplicate folder names",
            }
        )

    siblings = probe.get("software_siblings", [])
    if len(siblings) > 1:
        ideas.append(
            {
                "feature": "Multi-root library hub",
                "why": f"Sibling folders under _software: {siblings}",
                "action": "Scan extra roots from Flow editor + unified dashboard",
            }
        )

    ideas.append(
        {
            "feature": "Platform split view",
            "why": "Library mixes Win/Mac/quarantined — surface from folder names + extensions",
            "action": "Filter routes by platform; quarantine lane in flow",
        }
    )
    ideas.append(
        {
            "feature": "RELEASE_FILENAME harvester",
            "why": f"Top unverified ID method in reports: {reports.get('unverified_id_methods', [])}",
            "action": "Auto-suggest vendor_overrides from release prefixes (already partial in Vendors tab)",
        }
    )
    return ideas


def main() -> None:
    stamp = "20260629_0026"
    for arg in sys.argv[1:]:
        if re.match(r"\d{8}_\d{4}", arg):
            stamp = arg

    probe = probe_root(ROOT)
    probe["software_siblings"] = software_siblings()

    reports = analyze_reports(stamp) if (REPORT_DIR / f"Run_Summary_{stamp}.txt").is_file() else {}

    result = {
        "probe": probe,
        "reports": reports,
        "feature_ideas": feature_ideas(probe, reports),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
