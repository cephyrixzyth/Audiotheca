"""ML-SIM: spectral and metadata category classification."""

from __future__ import annotations

from typing import Any

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "impacts": ("hit", "impact", "slam", "punch", "crash", "bang", "kick"),
    "atmospheres": ("atmo", "amb", "drone", "pad", "room tone", "wind", "ambience"),
    "foley": ("foot", "cloth", "rustle", "foley", "movement", "step"),
    "ui": ("click", "beep", "ui", "button", "notification", "alert"),
    "music": ("loop", "stem", "melody", "chord", "bpm"),
    "dialogue": ("vox", "dialog", "dialogue", "voice", "speech"),
}


def classify_spectral(
    name: str,
    *,
    tags: list[str] | None = None,
    wav_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = " ".join([name, *(tags or [])]).lower()
    scores: dict[str, int] = {}
    for category, words in _KEYWORDS.items():
        scores[category] = sum(1 for w in words if w in text)

    if wav_info:
        duration = float(wav_info.get("duration_s") or 0)
        channels = int(wav_info.get("channels") or 1)
        if duration >= 30 and scores.get("atmospheres", 0) == 0:
            scores["atmospheres"] = scores.get("atmospheres", 0) + 1
        if duration <= 2 and scores.get("impacts", 0) == 0:
            scores["impacts"] = scores.get("impacts", 0) + 1
        if channels >= 6:
            scores["atmospheres"] = scores.get("atmospheres", 0) + 1

    best = max(scores, key=scores.get) if scores else "unknown"
    confidence_val = scores.get(best, 0)
    confidence = "high" if confidence_val >= 2 else "medium" if confidence_val == 1 else "none"
    return {
        "category": best if confidence_val else "unknown",
        "scores": scores,
        "confidence": confidence,
        "mode": "heuristic",
    }
