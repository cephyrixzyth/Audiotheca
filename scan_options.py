"""Scan run options — skip phases, alternate staging paths, extra roots."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


SKIPPABLE_PHASES = frozenset({
    "scene_peek",
    "archive_peek",
    "quarantine",
    "deep_identify",
    "ai_lookup",
    "malware_scan",
    "duplicates",
    "restructure",
    "restructure_live",
    "verification",
    "purge",
})


@dataclass
class ScanOptions:
    pause_between_phases: bool = False
    skip_phases: set[str] = field(default_factory=set)
    staging_root: str = ""
    extra_scan_roots: list[str] = field(default_factory=list)
    target_paths: list[str] = field(default_factory=list)
    invalidate_cache_paths: list[str] = field(default_factory=list)
    verbose_log: bool = False
    io_throttle_ms: int = 0
    max_workers: int = 0
    cooldown_s: float = 0.0

    def skip(self, phase: str) -> bool:
        return phase in self.skip_phases

    def to_dict(self) -> dict:
        return {
            "pause_between_phases": self.pause_between_phases,
            "skip_phases": sorted(self.skip_phases),
            "staging_root": self.staging_root,
            "extra_scan_roots": self.extra_scan_roots,
            "target_paths": self.target_paths,
            "invalidate_cache_paths": self.invalidate_cache_paths,
            "verbose_log": self.verbose_log,
            "io_throttle_ms": self.io_throttle_ms,
            "max_workers": self.max_workers,
            "cooldown_s": self.cooldown_s,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> ScanOptions:
        if not data:
            return cls()
        skip_raw = data.get("skip_phases") or []
        skip = {str(item).strip() for item in skip_raw if str(item).strip() in SKIPPABLE_PHASES}
        extra = [str(path).strip() for path in (data.get("extra_scan_roots") or []) if str(path).strip()]
        targets = [str(path).strip() for path in (data.get("target_paths") or []) if str(path).strip()]
        invalidate = [
            str(path).strip() for path in (data.get("invalidate_cache_paths") or []) if str(path).strip()
        ]
        return cls(
            pause_between_phases=bool(data.get("pause_between_phases")),
            skip_phases=skip,
            staging_root=str(data.get("staging_root") or "").strip(),
            extra_scan_roots=extra,
            target_paths=targets,
            invalidate_cache_paths=invalidate,
            verbose_log=bool(data.get("verbose_log")),
            io_throttle_ms=max(0, int(data.get("io_throttle_ms") or 0)),
            max_workers=max(0, int(data.get("max_workers") or 0)),
            cooldown_s=max(0.0, float(data.get("cooldown_s") or 0)),
        )


def load_scan_options() -> ScanOptions:
    raw = os.environ.get("AUDIOTHECA_SCAN_OPTIONS")
    if not raw:
        return ScanOptions()
    try:
        return ScanOptions.from_dict(json.loads(raw))
    except json.JSONDecodeError:
        return ScanOptions()


def apply_staging_paths(engine, options: ScanOptions) -> None:
    """Route quarantine/delete staging to alternate root when disk space is tight."""
    if not options.staging_root:
        return
    staging = Path(options.staging_root)
    engine.delete_candidates_dir = staging / "_delete-canidates"
    engine.quarantine_dir = staging / "_non_pc_quarantine"
    engine.logger.info(
        "Using alternate staging root: delete=%s quarantine=%s",
        engine.delete_candidates_dir,
        engine.quarantine_dir,
    )


def validate_staging_root(path: str) -> dict:
    """STG-ISOL: verify alternate staging root exists and is writable."""
    staging = Path(path)
    result = {
        "path": str(path),
        "valid": False,
        "exists": staging.exists(),
        "is_dir": staging.is_dir(),
        "writable": False,
        "delete_candidates": str(staging / "_delete-canidates"),
        "quarantine": str(staging / "_non_pc_quarantine"),
    }
    if not staging.is_dir():
        result["error"] = "not_a_directory" if staging.exists() else "missing"
        return result
    probe = staging / ".audiotheca_staging_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        result["writable"] = True
        result["valid"] = True
    except OSError as exc:
        result["error"] = str(exc)
    return result


def apply_scan_options(engine, options: ScanOptions) -> None:
    """Apply IO throttle and worker limits from scan options."""
    engine.scan_options = options
    engine.io_throttle_ms = max(0, int(options.io_throttle_ms or 0))
    if options.max_workers > 0:
        engine.max_workers = options.max_workers
        engine.logger.info("Scan max_workers overridden to %s", engine.max_workers)
    if engine.io_throttle_ms > 0:
        engine.logger.info("IO throttle enabled: %sms between scan batches", engine.io_throttle_ms)
