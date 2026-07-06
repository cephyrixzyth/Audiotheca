"""QRNT-RPR: quarantine repair analysis using malware heuristics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import malware_scanner as ms


def analyze_quarantine(path: str, *, root: str | Path | None = None) -> dict[str, Any]:
    target = Path(path)
    scan_root = Path(root) if root else target.parent
    assessment = ms.assess_file(target, root=scan_root) if target.is_file() else None
    deep = ms.deep_scan_file(target) if target.is_file() else {"status": "SKIPPED"}

    repairable = False
    recommendation = "keep_quarantined"
    injection_blocks: list[str] = []

    if assessment:
        injection_blocks.extend(assessment.get("reasons", []))
        if assessment.get("severity") == "LOW" and assessment.get("reasons") == ["installer_exe"]:
            repairable = True
            recommendation = "review_installer_context"

    if deep.get("status") == "CLEAN" and not injection_blocks:
        repairable = True
        recommendation = "likely_false_positive"

    if deep.get("status") == "THREAT":
        repairable = False
        recommendation = "keep_quarantined"
        injection_blocks.append("av_threat_detected")

    return {
        "path": str(target),
        "repairable": repairable,
        "injection_blocks": injection_blocks,
        "recommendation": recommendation,
        "assessment": assessment,
        "deep_scan": deep,
        "mode": "heuristic",
    }
