import csv
import hashlib
import json
import logging
import os
import re
import shutil
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
from job_control import PhaseStopRequested, phase_checkpoint
from progress import PhaseProgress, tqdm_bar
from restructure_feedback import (
    apply_override_to_paths,
    get_section_approvals,
    load_store as load_restructure_store,
)
from scan_options import ScanOptions, apply_scan_options, apply_staging_paths, load_scan_options
from vendor_db import VENDOR_DATABASE

from audiotheca.config import *  # noqa: F403
from audiotheca.coverage import discover_coverage_gaps
from audiotheca.session_log import log_step
from audiotheca.deep_identify import find_renamed_archive_dupes, needs_deep_identify, run_deep_identify
from audiotheca.helpers import _archive_stem, _limit_walk, _squash, _walk_depth
from audiotheca.verification import run_verification
from audiotheca.archive import ArchiveMixin
from audiotheca.dedupe import DedupeMixin
from audiotheca.identify import IdentifyMixin
from audiotheca.reports import ReportsMixin
from audiotheca.routing import RoutingMixin
from audiotheca.scan import ScanMixin
from audiotheca.platform_routing import OS_LANE_DIRS

from audiotheca.optional_deps import HAS_FUZZ, HAS_PEFILE, fuzz, pefile, tqdm

try:
    if not HAS_PEFILE:
        print("WARNING: 'pefile' not installed. PE binary header validation disabled.")
except Exception:
    pass

if tqdm is None:
    print("WARNING: 'tqdm' not installed. Progress bars disabled.")

if not HAS_FUZZ:
    print("WARNING: 'rapidfuzz' not installed. Falling back to token-overlap similarity.")

class DeduplicationEngine(
    ScanMixin,
    IdentifyMixin,
    DedupeMixin,
    RoutingMixin,
    ReportsMixin,
    ArchiveMixin,
):
    def __init__(self, root_dir: str | Path, dry_run: bool = DRY_RUN, max_workers: int = MAX_WORKERS):
        self.root_dir = Path(root_dir)
        self.dry_run = dry_run
        self.max_workers = max_workers
        self._lock = threading.Lock()
        self._paths: dict[str, Path] | None = None
        self.routes = self._compile_routes()
        self._setup_logging()
        self.run_stamp = datetime.now().strftime("%Y%m%d_%H%M")
        self.scan_cache = self._load_cache()

        self.quarantine_dir = self.root_dir / "_non_pc_quarantine"
        self.investigate_dir = self.root_dir / "_requiresinvestigation"
        self.delete_candidates_dir = self.root_dir / "_delete-canidates"
        self.tonex_dir = self.root_dir / "_tonex libraries"

        self.nested_issues: list[dict] = []
        self.coexistence_pairs: list[dict] = []
        self.duplicate_groups: list[dict] = []
        self.restructure_plan: list[dict] = []
        self.vendor_conflicts: list[dict] = []
        self.investigation_plan: list[dict] = []
        self.scan_failures: list[dict] = []
        self.archive_peek_rows: list[dict] = []
        self.scene_archive_rows: list[dict] = []
        self.multipart_diagnostics: list[dict] = []
        self.scene_rename_plan: list[dict] = []
        self.audit_rows: list[dict] = []
        self.audit_index_by_path: dict[str, int] = {}
        self.coverage_gaps: list[dict] = []
        self.cache_hit_records: list[dict] = []
        self.probe_truncations: list[dict] = []
        self.skip_phase_impact: dict[str, dict] = {}
        self.feedback_skipped_records: list[dict] = []
        self.deep_identify_rows: list[dict] = []
        self.ai_lookup_rows: list[dict] = []
        self.verification_findings: list[dict] = []
        self.quality_scorecard: dict = {}
        self.scan_options: ScanOptions = load_scan_options()
        self.io_throttle_ms = 0
        self._seven_zip = find_7z()
        self.action_mode = "preview"

        self.stats = {
            "scanned": 0,
            "scan_failures": 0,
            "cache_hits": 0,
            "routed": 0,
            "investigation": 0,
            "quarantined": 0,
            "duplicates_suspected": 0,
            "duplicates_confirmed": 0,
            "nested_issues": 0,
            "reconciled": 0,
            "deep_identified": 0,
            "errors": 0,
            "feedback_skipped": 0,
        }
        self.investigation_stats: dict[str, int] = defaultdict(int)
        self.investigation_store = load_investigation_store()
        self.restructure_store = load_restructure_store()
        self._stopped_by_user = False

    # ------------------------------------------------------------------
    # Setup / infrastructure
    # ------------------------------------------------------------------

    def _setup_logging(self) -> None:
        logging.basicConfig(
            filename=str(Path(__file__).resolve().parent.parent / "dedupe_engine.log"),
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            force=True,
        )
        self.logger = logging.getLogger(__name__)

    def _inc(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self.stats[key] = self.stats.get(key, 0) + amount

    @staticmethod
    def _needs_ai_lookup(item: dict) -> bool:
        from audiotheca.ai_lookup import needs_ai_lookup

        return needs_ai_lookup(item)

    def _confirm(self, prompt: str) -> bool:
        if self.dry_run:
            return True
        while True:
            choice = input(f"{prompt} [y/n]: ").strip().lower()
            if choice in {"y", "yes"}:
                return True
            if choice in {"n", "no"}:
                return False

    @staticmethod
    def _prompt_choice(prompt: str, options: dict[str, str]) -> str:
        keys = "/".join(options)
        while True:
            selection = input(f"{prompt} [{keys}]: ").strip().lower()
            if selection in options:
                return selection
            print("  " + " | ".join(f"{key} = {desc}" for key, desc in options.items()))

    def _print_live_preflight(self) -> bool:
        """Summarize planned live actions and require confirmation before Phase 3."""
        counts: dict[str, int] = defaultdict(int)
        for entry in self.restructure_plan:
            counts[entry["status"]] += 1

        high_dupes = sum(1 for group in self.duplicate_groups if group.get("confidence") == "HIGH")
        print("\n" + "=" * 60)
        print(" LIVE RUN PRE-FLIGHT ".center(60, "="))
        print("=" * 60)
        print(f"  Engine:             v{ENGINE_VERSION}")
        print(f"  Action mode:        {self.action_mode}")
        print(f"  Restructure routes: {len(self.restructure_plan)}")
        for status in sorted(counts, key=lambda key: -counts[key]):
            print(f"    {status}: {counts[status]}")
        print(f"  Scene renames:      {len(self.scene_rename_plan)}", end="")
        if SCENE_AUTO_RENAME:
            print(" (will apply, item-by-item)")
        else:
            print(" (plan only — Stage 2)")
        print(f"  Duplicate groups:   {len(self.duplicate_groups)} ({high_dupes} HIGH)")
        print("=" * 60)
        return self._confirm("Proceed with live filesystem changes?")

    def _resolve_action_mode(self) -> str:
        if self.dry_run:
            self.action_mode = "preview"
            return self.action_mode
        if ACTION_MODE in {"section", "item", "auto"}:
            self.action_mode = ACTION_MODE
            return self.action_mode
        choice = self._prompt_choice(
            "Live-run approval mode?",
            {
                "s": "section — approve each category bin in bulk",
                "i": "item — confirm every single move/stage action",
                "a": "auto — run all planned actions without prompts",
            },
        )
        self.action_mode = {"s": "section", "i": "item", "a": "auto"}[choice]
        print(f"  Using action mode: {self.action_mode}")
        return self.action_mode

    def _execute_actions(
        self,
        label: str,
        items: list,
        execute_one,
        describe_one,
        *,
        force_item_mode: bool = False,
    ) -> None:
        """Run a list of filesystem actions according to action_mode."""
        if not items:
            return
        if self.dry_run:
            for item in items:
                execute_one(item, dry_run=True)
            return

        if self.action_mode == "auto" and not force_item_mode:
            for item in items:
                execute_one(item, dry_run=False)
            return

        if self.action_mode == "section" and not force_item_mode:
            print(f"\n--- {label}: {len(items)} actions ---")
            for item in items[:12]:
                print(f"  {describe_one(item)}")
            if len(items) > 12:
                print(f"  ... and {len(items) - 12} more")
            if self._confirm(f"Proceed with all {len(items)} actions?"):
                for item in items:
                    execute_one(item, dry_run=False)
            else:
                print(f"  {label} skipped.")
                self.logger.info("%s skipped by user (%s items).", label, len(items))
            return

        skip_remaining = False
        print(f"\n--- {label}: {len(items)} actions (item-by-item) ---")
        for item in items:
            if skip_remaining:
                break
            choice = self._prompt_choice(
                describe_one(item),
                {"y": "yes", "n": "no", "s": "skip remaining"},
            )
            if choice == "y":
                execute_one(item, dry_run=False)
            elif choice == "s":
                skip_remaining = True
                self.logger.info("%s: user skipped remaining items.", label)

    def _checkpoint(self, phase_id: str, phase_label: str) -> None:
        phase_checkpoint(
            phase_id,
            phase_label,
            pause_between_phases=self.scan_options.pause_between_phases,
        )

    @staticmethod
    def _audit_flags(item: dict, *, inv_bucket: str = "", status: str = "") -> str:
        flags: list[str] = []
        if not item.get("company"):
            flags.append("unknown_vendor")
        elif item.get("id_confidence") == "TENTATIVE":
            flags.append("tentative_id")
        method = item.get("id_method", "")
        if method in {"NFO", "NAME_SPLIT", "RECONCILED", "FUZZY_VENDOR", "SIBLING_INFERENCE"}:
            flags.append(f"weak:{method.lower()}")
        if inv_bucket:
            flags.append(f"inv:{inv_bucket}")
        if status and status != "READY":
            flags.append(f"status:{status.replace(' ', '_').lower()}")
        if item.get("is_tonex"):
            flags.append("tonex")
        return ";".join(flags)

    def _append_audit_row(
        self,
        item: dict,
        *,
        status: str,
        inv_bucket: str,
        destination: str,
        extra_flags: str = "",
    ) -> None:
        self._upsert_audit_row(
            item,
            status=status,
            inv_bucket=inv_bucket,
            destination=destination,
            extra_flags=extra_flags,
        )

    def _upsert_audit_row(
        self,
        item: dict,
        *,
        status: str,
        inv_bucket: str,
        destination: str,
        extra_flags: str = "",
    ) -> None:
        path_key = str(item["path"])
        flags = self._audit_flags(item, inv_bucket=inv_bucket, status=status)
        if extra_flags:
            flags = f"{flags};{extra_flags}" if flags else extra_flags
        row = {
            "section": item["source_bin"],
            "item_name": item["original_name"],
            "current_path": path_key,
            "vendor": item.get("company") or "UNKNOWN",
            "id_method": item.get("id_method") or "",
            "id_confidence": item.get("id_confidence") or "",
            "fingerprint": item.get("base_name") or "",
            "version_key": item.get("version_key") or "",
            "size_mb": round(item.get("size", 0) / (1024 * 1024), 1) if item.get("size") else "",
            "status": status,
            "investigation_bucket": inv_bucket or "",
            "planned_destination": destination,
            "flags": flags,
        }
        with self._lock:
            if path_key in self.audit_index_by_path:
                self.audit_rows[self.audit_index_by_path[path_key]] = row
            else:
                self.audit_index_by_path[path_key] = len(self.audit_rows)
                self.audit_rows.append(row)

    def _record_cache_hit(self, path: Path, source_bin: str) -> None:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = None
        with self._lock:
            self.cache_hit_records.append(
                {
                    "section": source_bin,
                    "path": str(path),
                    "name": path.name,
                    "mtime": mtime,
                }
            )

    def _record_probe_truncation(self, item_path: Path, source_bin: str, trunc: dict) -> None:
        with self._lock:
            self.probe_truncations.append(
                {
                    "section": source_bin,
                    "item_path": str(item_path),
                    "item_name": item_path.name,
                    "kind": trunc.get("kind", ""),
                    "path": trunc.get("path", ""),
                    "relative_path": trunc.get("relative_path", ""),
                    "depth": trunc.get("depth", ""),
                    "limit": trunc.get("limit", ""),
                    "detail": (
                        f"dirs={trunc.get('child_dirs', trunc.get('folder_count', ''))} "
                        f"files={trunc.get('child_files', trunc.get('archive_count', ''))}"
                    ),
                }
            )

    def _record_skip_impact(self, phase: str, count: int, detail: str = "") -> None:
        self.skip_phase_impact[phase] = {"count": count, "detail": detail}

    def _invalidate_cache_paths(self) -> None:
        for raw in self.scan_options.invalidate_cache_paths:
            key = str(Path(raw))
            if key in self.scan_cache:
                del self.scan_cache[key]
                self.logger.info("Cache invalidated for %s", key)

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self) -> str:
        """Run the engine. Returns 'stopped' if user stopped, else 'ok'."""
        print("\n" + "=" * 60)
        print(f" AUDIO DEDUPLICATION ENGINE v{ENGINE_VERSION} ".center(60, "="))
        print("=" * 60)
        print(f" VERSION: {ENGINE_VERSION}")
        print(f" ROOT: {self.root_dir}")
        print(f" DRY_RUN: {self.dry_run}")
        print(f" MAX_WALK_DEPTH: {MAX_WALK_DEPTH} | PROBE_DEPTH: {PROBE_DEPTH} | WORKERS: {self.max_workers}")
        print(f" ARCHIVE_PEEK: {ENABLE_ARCHIVE_PEEK} | SCENE_PEEK: {ENABLE_SCENE_ARCHIVE_PEEK} | SCENE_RENAME: {SCENE_AUTO_RENAME}")
        if self.scan_options.skip_phases:
            print(f" SKIP PHASES: {', '.join(sorted(self.scan_options.skip_phases))}")
        if self.scan_options.staging_root:
            print(f" STAGING ROOT: {self.scan_options.staging_root}")
        if self.scan_options.pause_between_phases:
            print(" PAUSE BETWEEN PHASES: enabled (UI can continue/stop at each step)")
        print(f" 7-ZIP: {self._seven_zip or 'NOT FOUND - install 7-Zip for .rar/.7z listing'}")
        print(f" REPORTS: {REPORT_DIR}")
        print("=" * 60 + "\n")

        if not self.root_dir.exists():
            print("[X] ERROR: Cannot reach network share.")
            self.logger.critical("Cannot reach network share: %s", self.root_dir)
            return

        if not self.dry_run and not os.access(self.root_dir, os.W_OK):
            print("[X] ERROR: Drive is read-only.")
            return

        self.logger.info("Engine v%s started | DRY_RUN=%s | ROOT=%s", ENGINE_VERSION, self.dry_run, self.root_dir)

        apply_staging_paths(self, self.scan_options)
        apply_scan_options(self, self.scan_options)
        self._invalidate_cache_paths()

        paths = self._report_paths()
        csv_file = open(paths["org_csv"], "w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["Action", "Item Name", "Source Category", "Destination", "Notes", "Detected Vendor"])

        inv_file = None
        inv_writer = None
        if GENERATE_INVENTORY_DUMP:
            inv_file = open(paths["inventory_csv"], "w", newline="", encoding="utf-8")
            inv_writer = csv.writer(inv_file)
            inv_writer.writerow(
                ["Root Bin", "Item Name", "Extracted Fingerprint", "Version Key", "Type", "Detected Vendor", "ID Method", "Tonex"]
            )

        try:
            self._run_phases(csv_writer, inv_writer)
        except PhaseStopRequested as exc:
            self._stopped_by_user = True
            print(f"\n[!] Run stopped at phase checkpoint ({exc}). Writing partial reports.")
            self.logger.info("Run stopped by user at phase checkpoint: %s", exc)
        except KeyboardInterrupt:
            print("\n[!] Interrupted — writing partial reports.")
            self.logger.warning("Run interrupted by user.")
        except Exception as exc:
            print(f"\n[X] Run aborted: {exc} — writing partial reports.")
            self.logger.critical("Run aborted: %s", exc, exc_info=True)
        finally:
            csv_file.close()
            if inv_file:
                inv_file.close()
            self._save_cache()
            report_paths = self.write_reports()
            hints_path = export_engine_hints()
            inv_hints_path = export_investigation_hints()
            self.logger.info("Engine hints refreshed: %s, %s", hints_path, inv_hints_path)
            self._print_summary(report_paths)
        return "stopped" if self._stopped_by_user else "ok"

    def _run_phases(self, csv_writer, inv_writer) -> None:
        if not self.dry_run:
            self._resolve_action_mode()

        category_bins = [
            entry
            for entry in self.root_dir.iterdir()
            if entry.is_dir() and entry.name not in IGNORE_BINS
        ]
        for extra_root in self.scan_options.extra_scan_roots:
            extra_path = Path(extra_root)
            if not extra_path.is_dir():
                self.logger.warning("Extra scan root not found: %s", extra_path)
                continue
            for entry in extra_path.iterdir():
                if entry.is_dir() and entry.name not in IGNORE_BINS:
                    category_bins.append(entry)

        bin_progress = PhaseProgress("Phase 1a - Resolve targets per category", len(category_bins), "section")
        self._bin_progress = bin_progress
        payloads: list[tuple[Path, str]] = []
        bin_targets: dict[str, list[Path]] = {}

        if self.scan_options.target_paths:
            for raw in self.scan_options.target_paths:
                target = Path(raw)
                if not target.exists():
                    self.logger.warning("Target path not found: %s", target)
                    continue
                section = target.parent.name if target.parent else "adhoc"
                expanded = self.expand_single_target(target, section)
                if not expanded:
                    expanded = [target]
                for item in expanded:
                    payloads.append((item, section))
                    bin_targets.setdefault(section, []).append(item)
            bin_progress.finish(f"{len(payloads):,} ad-hoc targets")
        else:
            for category_bin in category_bins:
                log_step("get_software_targets", f"Resolving bin {category_bin.name}")
                bin_progress.pulse(detail=f"Starting {category_bin.name}…")
                targets = self.get_software_targets(category_bin)
                bin_targets[category_bin.name] = targets
                payloads.extend((target, category_bin.name) for target in targets)
                bin_progress.update(1, detail=f"{category_bin.name}: {len(targets)} targets")
            bin_progress.finish(f"{len(payloads):,} total targets")
            self._bin_progress = None

        if not self.scan_options.target_paths:
            gap_progress = PhaseProgress(
                "Phase 1a.5 - Coverage gap scan", len(category_bins), "section"
            )
            for category_bin in category_bins:
                gaps = discover_coverage_gaps(category_bin, bin_targets.get(category_bin.name, []))
                self.coverage_gaps.extend(gaps)
                gap_progress.update(1, detail=f"{len(gaps)} gaps in {category_bin.name}")
            gap_progress.finish(f"{len(self.coverage_gaps):,} coverage gaps")
        self._checkpoint("resolve_targets", "Phase 1a - Resolve targets per category")

        if not payloads:
            print("\n[!] WARNING: Found 0 targets.")
            return

        scan_progress = PhaseProgress("Phase 1b - Parallel scan", len(payloads), "item")
        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._scan_worker, path, bin_name): path
                for path, bin_name in payloads
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
                scan_progress.update(1)
        scan_progress.finish(f"{len(results):,} items scanned")
        self._checkpoint("parallel_scan", "Phase 1b - Parallel scan")

        if not self.scan_options.skip("malware_scan"):
            import malware_scanner as ms

            max_malware_files = 25_000
            malware_progress = PhaseProgress(
                "Phase 1.4 - Malware scan", max_malware_files, "file"
            )

            def _malware_progress(scanned: int, detail: str) -> None:
                malware_progress.update(min(scanned, max_malware_files), detail=detail[:120])

            findings = ms.scan_tree(
                self.root_dir,
                max_files=max_malware_files,
                use_clamav=False,
                progress_cb=_malware_progress,
            )
            if findings:
                report_path = ms.write_scan_report(self.root_dir, findings)
                self.logger.warning(
                    "Malware scan: %d suspicious files — report %s",
                    len(findings),
                    report_path.name,
                )
            malware_progress.finish(
                f"{len(findings)} suspicious file(s) from heuristic scan"
            )
        else:
            print("  [SKIP] Malware scan disabled by scan options.")
        self._checkpoint("malware_scan", "Phase 1.4 - Malware scan")

        results.sort(key=lambda r: (r["source_bin"], r["original_name"].lower()))

        all_items: list[dict] = []

        for item in results:
            self._inc("scanned")

            for nested in item["nested"]:
                self.nested_issues.append(
                    {"source_bin": item["source_bin"], "item_name": item["original_name"], **nested}
                )
            self._inc("nested_issues", len(item["nested"]))

            all_items.append(item)

        off_lane_count = sum(1 for item in all_items if item.get("platform_lane"))
        if off_lane_count and self.scan_options.skip("quarantine"):
            self._record_skip_impact(
                "quarantine",
                off_lane_count,
                f"{off_lane_count} off-native OS items left in category bins",
            )
            print(
                f"  [SKIP] OS lane routing disabled — {off_lane_count} Mac/Linux/Windows "
                "items will keep native paths in the restructure plan."
            )
        elif off_lane_count:
            print(
                f"  OS lane routing: {off_lane_count} items will route under "
                f"_mac / _linux / _windows when restructure runs."
            )
        self._checkpoint("quarantine", "Phase 1b - OS lane routing flags")

        reconcile_progress = PhaseProgress("Phase 1.5 - Vendor reconciliation", len(all_items), "item")
        reconciled = self.reconcile_vendors(all_items)
        reconcile_progress.finish(
            f"{reconciled} reconciled, {len(self.vendor_conflicts)} fingerprint conflicts"
        )
        self._checkpoint("reconciliation", "Phase 1.5 - Vendor reconciliation")

        if not self.scan_options.skip("deep_identify"):
            candidates = sum(1 for item in all_items if needs_deep_identify(item))
            deep_progress = PhaseProgress(
                "Phase 1.7 - Deep identification", max(candidates, 1), "item"
            )
            self.deep_identify_rows = run_deep_identify(
                all_items,
                self.vendor_aliases,
                self._name_similarity,
                progress_cb=lambda detail: deep_progress.update(1, detail=detail),
            )
            with self._lock:
                self.stats["deep_identified"] = len(self.deep_identify_rows)
            deep_progress.finish(
                f"{len(self.deep_identify_rows)} vendors recovered "
                f"(fuzzy + sibling inference) from {candidates} candidates"
            )
        else:
            candidates = sum(1 for item in all_items if needs_deep_identify(item))
            self._record_skip_impact(
                "deep_identify",
                candidates,
                f"{candidates} unknown/tentative items not deep-identified",
            )
            print("  [SKIP] Deep identification disabled by scan options.")
        self._checkpoint("deep_identify", "Phase 1.7 - Deep identification")

        if not self.scan_options.skip("ai_lookup"):
            ai_candidates = [item for item in all_items if self._needs_ai_lookup(item)]
            if ai_candidates:
                from audiotheca.ai_lookup import queue_ai_lookups

                ai_progress = PhaseProgress(
                    "Phase 1b-fallback - AI lookup", max(len(ai_candidates), 1), "item"
                )
                self.ai_lookup_rows = [r.to_dict() for r in queue_ai_lookups(
                    all_items,
                    root=self.root_dir,
                    max_items=50,
                    progress_cb=lambda _evt: ai_progress.update(1),
                )]
                ai_progress.finish(f"{len(self.ai_lookup_rows)} AI lookups queued")
            else:
                self.ai_lookup_rows = []
        else:
            self.ai_lookup_rows = []
            print("  [SKIP] AI lookup disabled by scan options.")
        self._checkpoint("ai_lookup", "Phase 1b-fallback - AI lookup")

        if ENABLE_SCENE_ARCHIVE_PEEK and not self.scan_options.skip("scene_peek"):
            self._run_scene_archive_phase(all_items, csv_writer)
        elif self.scan_options.skip("scene_peek"):
            scene_count = sum(
                1 for item in all_items if SCENE_RELEASE_PATTERN.match(item["original_name"])
            )
            self._record_skip_impact(
                "scene_peek",
                scene_count,
                f"{scene_count} scene-hash folders not peeked",
            )
            print("  [SKIP] Scene archive peek disabled by scan options.")
        self._checkpoint("scene_peek", "Phase 1.6 - Scene archive peek")

        if ENABLE_ARCHIVE_PEEK and not self.scan_options.skip("archive_peek"):
            self._run_archive_peek_phase()
        elif self.scan_options.skip("archive_peek"):
            self._record_skip_impact(
                "archive_peek",
                len(self.coexistence_pairs),
                f"{len(self.coexistence_pairs)} coexistence pairs not peeked",
            )
            print("  [SKIP] Archive peek disabled by scan options.")
        self._checkpoint("archive_peek", "Phase 1.8 - Archive peek")

        dedup_groups: dict[str, list[dict]] = defaultdict(list)
        for item in all_items:
            if inv_writer:
                inv_writer.writerow(
                    [
                        item["source_bin"],
                        item["original_name"],
                        item["base_name"],
                        item["version_key"],
                        "DIR" if item["is_dir"] else "ARCHIVE",
                        item["company"] or "UNKNOWN",
                        item["id_method"],
                        "YES" if item["is_tonex"] else "NO",
                    ]
                )

            dedup_key = self.build_dedup_key(item)
            if dedup_key:
                dedup_groups[dedup_key].append(item)

        feedback_store = load_feedback_store()

        archive_pairs = self.find_cross_item_archive_pairs(all_items)
        archive_pair_path_sets = {
            frozenset(item["path"] for item in pair["items"]) for pair in archive_pairs
        }
        for pair in archive_pairs:
            if pair["confidence"] == "LOW":
                continue
            pair_paths = [str(item["path"]) for item in pair["items"]]
            if is_group_rejected(pair["dedup_key"], pair_paths, feedback_store):
                self._inc("feedback_skipped")
                self.feedback_skipped_records.append(
                    {
                        "dedup_key": pair["dedup_key"],
                        "kind": "archive_pair",
                        "paths": pair_paths,
                        "confidence": pair["confidence"],
                    }
                )
                print(f"\n[SKIP FEEDBACK] {pair['dedup_key']} — user rejected this match")
                continue
            self.duplicate_groups.append(pair)
            self._inc("duplicates_suspected")
            print(
                f"\n[ARCHIVE PAIR {pair['confidence']}] {pair['dedup_key']} "
                f"(similarity {pair['name_similarity']}%, size ratio {pair['size_ratio']})"
            )
            for idx, item in enumerate(pair["items"], 1):
                size_mb = item["size"] / (1024 * 1024)
                kind = "ARCHIVE" if not item["is_dir"] else "FOLDER"
                rec = " <-- suggested keep" if item["path"] == pair["recommended_keep"]["path"] else ""
                print(f"  [{idx}] [{kind}] {item['original_name']} ({size_mb:.1f} MB){rec}")

        dupe_candidates = [items for items in dedup_groups.values() if len(items) >= 2]

        if not self.scan_options.skip("duplicates"):
            renamed_groups = find_renamed_archive_dupes(all_items, self.sparse_hash)
            for group in renamed_groups:
                pair_paths = [str(item["path"]) for item in group["items"]]
                if frozenset(item["path"] for item in group["items"]) in archive_pair_path_sets:
                    continue
                if is_group_rejected(group["dedup_key"], pair_paths, feedback_store):
                    self._inc("feedback_skipped")
                    self.feedback_skipped_records.append(
                        {
                            "dedup_key": group["dedup_key"],
                            "kind": "renamed_copy",
                            "paths": pair_paths,
                            "confidence": group["confidence"],
                        }
                    )
                    continue
                self.duplicate_groups.append(group)
                self._inc("duplicates_suspected")
                print(
                    f"\n[RENAMED COPY {group['confidence']}] {group['dedup_key']} "
                    f"— byte-identical archives with different names"
                )
                for idx, item in enumerate(group["items"], 1):
                    size_mb = item["size"] / (1024 * 1024)
                    rec = " <-- suggested keep" if item["path"] == group["recommended_keep"]["path"] else ""
                    print(f"  [{idx}] {item['original_name']} ({size_mb:.1f} MB) in {item['source_bin']}{rec}")

        items_to_delete: list[dict] = []
        if self.scan_options.skip("duplicates"):
            skipped_groups = len(dupe_candidates)
            self._record_skip_impact(
                "duplicates",
                skipped_groups,
                f"{skipped_groups} duplicate candidate groups not reviewed",
            )
            print(f"  [SKIP] Duplicate review disabled — {skipped_groups} candidate groups skipped.")
            dupe_progress = PhaseProgress("Phase 2 - Duplicate review", 1, "group")
            dupe_progress.finish("skipped by scan options")
        else:
            dupe_progress = PhaseProgress("Phase 2 - Duplicate review", len(dupe_candidates), "group")

            for dedup_key, items in dedup_groups.items():
                if len(items) < 2:
                    continue
                if frozenset(item["path"] for item in items) in archive_pair_path_sets:
                    continue
                item_paths = [str(item["path"]) for item in items]
                if is_group_rejected(dedup_key, item_paths, feedback_store):
                    self._inc("feedback_skipped")
                    self.feedback_skipped_records.append(
                        {
                            "dedup_key": dedup_key,
                            "kind": "duplicate_group",
                            "paths": item_paths,
                            "confidence": "",
                        }
                    )
                    print(f"\n[SKIP FEEDBACK] {dedup_key} — user rejected this match")
                    continue

                dupe_progress.update(1, detail=dedup_key[:40])
                assessment = self.assess_duplicate_group(items)
                if assessment["confidence"] == "LOW":
                    continue

                is_vendor_collision = any(
                    item["company"] and _squash(item["company"]) == item["base_name"] for item in items
                )
                if is_vendor_collision:
                    continue

                if assessment["confidence"] == "HIGH":
                    content = self._content_check(assessment["items"])
                    assessment["content_check"] = content
                    if content == "DIFFERS":
                        assessment["confidence"] = "MEDIUM"

                if self.dry_run:
                    action = "REVIEW ONLY (no files removed in DRY_RUN)"
                elif assessment["confidence"] == "HIGH":
                    action = "PROMPT to backup non-recommended copies"
                else:
                    action = "REVIEW ONLY (MEDIUM confidence)"

                group_record = {"dedup_key": dedup_key, **assessment, "action": action}
                self.duplicate_groups.append(group_record)
                self._inc("duplicates_suspected")

                print(
                    f"\n[DUPLICATE {assessment['confidence']}] {dedup_key} "
                    f"({assessment['group_kind']}, similarity {assessment['name_similarity']}%, "
                    f"content {assessment.get('content_check', 'SKIPPED')})"
                )
                for idx, item in enumerate(assessment["items"], 1):
                    size_mb = item["size"] / (1024 * 1024)
                    rec = " <-- suggested keep" if item["path"] == assessment["recommended_keep"]["path"] else ""
                    print(f"  [{idx}] {item['original_name']} ({size_mb:.1f} MB) in {item['source_bin']}{rec}")

                if self.dry_run or assessment["confidence"] != "HIGH":
                    continue

                keep = assessment["recommended_keep"]
                candidates = [item for item in assessment["items"] if item["path"] != keep["path"]]
                if not candidates:
                    continue

                if self.action_mode == "auto":
                    if assessment.get("content_check") == "MATCH":
                        items_to_delete.extend(candidates)
                    continue

                if self.action_mode == "item":
                    skip_group = False
                    for candidate in candidates:
                        if skip_group:
                            break
                        size_mb = candidate["size"] / (1024 * 1024)
                        choice = self._prompt_choice(
                            f"Stage duplicate '{candidate['original_name']}' ({size_mb:.1f} MB) "
                            f"to {self.delete_candidates_dir.name}?",
                            {"y": "yes", "n": "no", "s": "skip remaining in group"},
                        )
                        if choice == "y":
                            items_to_delete.append(candidate)
                        elif choice == "s":
                            skip_group = True
                    continue

                items_sorted = assessment["items"]
                while True:
                    choice = input(
                        "Select index to KEEP — others move to _delete-canidates (Enter = keep all): "
                    ).strip()
                    if choice == "":
                        break
                    if choice.isdigit() and 1 <= int(choice) <= len(items_sorted):
                        chosen_idx = int(choice) - 1
                        for idx, item in enumerate(items_sorted):
                            if idx != chosen_idx:
                                items_to_delete.append(item)
                        break
                    print("Invalid index.")

            dupe_progress.finish(f"{len(self.duplicate_groups)} groups flagged")
        self._checkpoint("duplicates", "Phase 2 - Duplicate review")

        if items_to_delete:
            if not self.dry_run:
                self.delete_candidates_dir.mkdir(exist_ok=True)
            for item in items_to_delete:
                status = "[DRY RUN] Would stage" if self.dry_run else "Staged for deletion"
                csv_writer.writerow(
                    [
                        status,
                        item["original_name"],
                        item["source_bin"],
                        self.delete_candidates_dir.name,
                        "Confirmed duplicate",
                        item["company"] or "Unknown",
                    ]
                )
                self._inc("duplicates_confirmed")
                if not self.dry_run:
                    self.safe_move(item["path"], self.delete_candidates_dir / item["original_name"])

        restructure_progress = PhaseProgress("Phase 3 - Restructure plan", len(all_items), "item")
        delete_paths = {entry["path"] for entry in items_to_delete}
        conflict_bases = {c["base_name"] for c in self.vendor_conflicts}
        confirmed_bases = self._confirmed_base_vendors(all_items)

        if self.scan_options.skip("restructure"):
            print("[!] Phase 3 restructure plan skipped (scan options).")
            self.logger.info("Phase 3 restructure plan skipped via scan options.")
        else:
            for item in all_items:
                if item["path"] in delete_paths:
                    continue

                dest_path, relative_dest, route_status, inv_bucket = self.compute_destination(
                    item,
                    conflict_bases=conflict_bases,
                    confirmed_bases=confirmed_bases,
                )
                if not inv_bucket:
                    dest_path, relative_dest = apply_override_to_paths(
                        self.root_dir,
                        str(item["path"]),
                        dest_path,
                        relative_dest,
                        self.restructure_store,
                    )
                vendor = item["company"] or "UNKNOWN"
                if inv_bucket:
                    _bucket, reason = self.classify_investigation(
                        item,
                        conflict_bases=conflict_bases,
                        confirmed_bases=confirmed_bases,
                    )
                    status = route_status
                    self._inc("investigation")
                    self.investigation_stats[inv_bucket] += 1
                    self.investigation_plan.append(
                        {
                            "source_bin": item["source_bin"],
                            "original_name": item["original_name"],
                            "current_path": str(item["path"]),
                            "destination": str(dest_path),
                            "bucket": inv_bucket,
                            "reason": reason,
                            "id_method": item["id_method"],
                            "id_confidence": item["id_confidence"],
                            "base_name": item["base_name"],
                            "size_mb": round(item["size"] / (1024 * 1024), 1),
                        }
                    )
                elif dest_path.exists():
                    status = "DEST EXISTS (merge)"
                else:
                    status = route_status if route_status != "READY" else "READY"

                self.restructure_plan.append(
                    {
                        "source_bin": item["source_bin"],
                        "original_name": item["original_name"],
                        "current_path": str(item["path"]),
                        "destination": str(dest_path),
                        "relative_dest": relative_dest,
                        "vendor": vendor,
                        "id_method": item["id_method"],
                        "id_confidence": item["id_confidence"],
                        "display_name": item["display_name"],
                        "version_key": item["version_key"],
                        "base_name": item["base_name"],
                        "size_mb": round(item["size"] / (1024 * 1024), 1),
                        "status": status,
                        "investigation_bucket": inv_bucket,
                        "_item": item,
                        "_dest_path": dest_path,
                    }
                )
                self._append_audit_row(
                    item,
                    status=status,
                    inv_bucket=inv_bucket or "",
                    destination=str(dest_path),
                )
                restructure_progress.update(1, detail=item["original_name"][:36])

            restructure_progress.finish(f"{len(self.restructure_plan)} routes, {self.stats['investigation']} investigation")
        self._checkpoint("restructure", "Phase 3 - Restructure plan")

        if not self.scan_options.skip("verification"):
            verify_progress = PhaseProgress("Phase 3.5 - Verification", 1, "pass")
            self.quality_scorecard, self.verification_findings = run_verification(
                all_items,
                duplicate_groups=self.duplicate_groups,
                investigation_plan=self.investigation_plan,
                restructure_plan=self.restructure_plan,
                vendor_aliases=self.vendor_aliases,
                build_dedup_key=self.build_dedup_key,
            )
            score = self.quality_scorecard
            verify_progress.finish(
                f"identification {score['identification_rate_pct']}% "
                f"({score['confirmed_rate_pct']}% confirmed), "
                f"routes ready {score['route_ready_pct']}%, "
                f"{score['findings_warnings']} warnings, "
                f"{score['findings_suggestions']} suggestions"
            )
            for finding in self.verification_findings:
                marker = "[!]" if finding["severity"] == "WARNING" else "[i]"
                print(f"  {marker} {finding['check']}: {finding['detail'][:110]}")
        else:
            print("  [SKIP] Verification pass disabled by scan options.")
        self._checkpoint("verification", "Phase 3.5 - Verification")

        if self.dry_run:
            for entry in self.restructure_plan:
                csv_writer.writerow(
                    [
                        "[DRY RUN] Would move to",
                        entry["original_name"],
                        entry["source_bin"],
                        entry["relative_dest"],
                        entry["status"],
                        entry["vendor"],
                    ]
                )
                self._inc("routed")
        elif not self.scan_options.skip("restructure_live") and self._print_live_preflight():
            self._execute_restructure(csv_writer)
        elif self.scan_options.skip("restructure_live"):
            print("[!] Phase 3 live restructure skipped (scan options).")
        else:
            print("[!] Phase 3 restructure skipped (declined at pre-flight).")
            self.logger.info("Phase 3 restructure skipped at pre-flight.")
        self._checkpoint("restructure_live", "Phase 3 - Restructure moves")

        if not self.dry_run and not self.scan_options.skip("purge"):
            purge_roots: list[Path] = []
            for top in self.root_dir.iterdir():
                if not top.is_dir():
                    continue
                if top.name in OS_LANE_DIRS:
                    purge_roots.extend(
                        child for child in top.iterdir() if child.is_dir()
                    )
                elif top.name not in IGNORE_BINS:
                    purge_roots.append(top)

            def _purge_bin(category_bin: Path, *, dry_run: bool = False) -> None:
                if dry_run:
                    return
                try:
                    for dirpath, dirs, _filenames in os.walk(category_bin, topdown=False):
                        _limit_walk(category_bin, dirpath, dirs)
                        if not os.listdir(dirpath):
                            try:
                                os.rmdir(dirpath)
                            except OSError:
                                pass
                except (OSError, PermissionError) as exc:
                    self.logger.warning("Empty-dir purge failed in %s: %s", category_bin, exc)

            self._execute_actions(
                "Phase 4: Purge empty wrapper directories",
                purge_roots,
                lambda category_bin, dry_run=False: _purge_bin(category_bin, dry_run=dry_run),
                lambda category_bin: f"Purge empty dirs under {category_bin.name}/",
            )

    def _apply_restructure_entry(self, entry: dict, csv_writer, *, dry_run: bool = False) -> None:
        if dry_run:
            csv_writer.writerow(
                [
                    "[DRY RUN] Would move to",
                    entry["original_name"],
                    entry["source_bin"],
                    entry["relative_dest"],
                    entry["status"],
                    entry["vendor"],
                ]
            )
            self._inc("routed")
            return

        item = entry["_item"]
        dest_path = entry["_dest_path"]
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.logger.error("Cannot create %s: %s", dest_path.parent, exc)
            self._inc("errors")
            entry["status"] = "MOVE FAILED"
            csv_writer.writerow(
                ["FAILED", entry["original_name"], entry["source_bin"], entry["relative_dest"], "mkdir failed — see log", entry["vendor"]]
            )
            return

        if item["is_dir"]:
            moved = self.move_and_merge(item["path"], dest_path)
        else:
            moved = self.safe_move(item["path"], dest_path)

        if moved:
            sidecar_data = {**item, "investigation_bucket": entry.get("investigation_bucket", "")}
            self.write_sidecar_metadata(dest_path, sidecar_data)
            self._inc("routed")
            csv_writer.writerow(
                ["Organized to", entry["original_name"], entry["source_bin"], entry["relative_dest"], entry["status"], entry["vendor"]]
            )
        else:
            entry["status"] = "MOVE FAILED"
            csv_writer.writerow(
                ["FAILED", entry["original_name"], entry["source_bin"], entry["relative_dest"], "Move failed — see log", entry["vendor"]]
            )

    def _execute_restructure(self, csv_writer) -> None:
        """Live-run execution with section bulk or item-by-item approval."""
        if self.action_mode == "item" or self.action_mode == "auto":
            ordered = sorted(
                self.restructure_plan,
                key=lambda entry: (entry["source_bin"], entry["original_name"].lower()),
            )
            self._execute_actions(
                "Phase 3: Restructure moves",
                ordered,
                lambda entry, dry_run=False: self._apply_restructure_entry(entry, csv_writer, dry_run=dry_run),
                lambda entry: f"{entry['original_name']} -> {entry['relative_dest']}/ ({entry['status']})",
            )
            return

        by_section: dict[str, list[dict]] = defaultdict(list)
        for entry in self.restructure_plan:
            by_section[entry["source_bin"]].append(entry)

        skip_remaining = False
        ui_approved = get_section_approvals(store=self.restructure_store)
        for section in sorted(by_section):
            entries = by_section[section]

            if skip_remaining:
                selection = "s"
            elif section in ui_approved:
                print(f"\n--- Section '{section}': {len(entries)} moves (pre-approved in UI) ---")
                selection = "a"
            else:
                print(f"\n--- Section '{section}': {len(entries)} planned moves ---")
                for entry in entries[:15]:
                    print(f"  {entry['original_name']} -> {entry['relative_dest']}/")
                if len(entries) > 15:
                    print(f"  ... and {len(entries) - 15} more (see Restructure CSV)")
                selection = self._prompt_choice(
                    f"Approve {len(entries)} moves for section '{section}'?",
                    {"a": "approve", "s": "skip section", "q": "skip this and all remaining"},
                )
                if selection == "q":
                    skip_remaining = True
                    selection = "s"

            if selection == "s":
                print(f"  Section '{section}' skipped.")
                self.logger.info("Section %s skipped by user (%s items).", section, len(entries))
                for entry in entries:
                    entry["status"] = "SKIPPED BY USER"
                    csv_writer.writerow(
                        [
                            "Skipped by user",
                            entry["original_name"],
                            entry["source_bin"],
                            entry["relative_dest"],
                            "Section not approved",
                            entry["vendor"],
                        ]
                    )
                continue

            for entry in entries:
                self._apply_restructure_entry(entry, csv_writer)

    def _print_summary(self, report_paths: dict[str, Path]) -> None:
        high = sum(1 for g in self.duplicate_groups if g["confidence"] == "HIGH")
        medium = sum(1 for g in self.duplicate_groups if g["confidence"] == "MEDIUM")

        print("\n" + "=" * 60)
        print(f" SCAN COMPLETE (v{ENGINE_VERSION}) ".center(60, "="))
        print("=" * 60)
        print(
            f"  Scanned: {self.stats['scanned']} (cache hits: {self.stats['cache_hits']}, "
            f"failures: {self.stats['scan_failures']}) | Routes planned: {self.stats['routed']}"
        )
        if self.scan_failures:
            print(f"  Scan failures: {len(self.scan_failures)} (see Scan_Failures CSV)")
        print(f"  Investigation: {self.stats['investigation']}", end="")
        if self.investigation_stats:
            top_buckets = sorted(self.investigation_stats.items(), key=lambda row: -row[1])[:4]
            print(" (" + ", ".join(f"{b}: {c}" for b, c in top_buckets) + ")")
        else:
            print()
        print(
            f"  OS lanes (_mac/_linux/_windows): {self.stats['quarantined']} | "
            f"Nested: {len(self.nested_issues)} | Coexistence: {len(self.coexistence_pairs)} | "
            f"Errors: {self.stats['errors']}"
        )
        print(
            f"  Reconciled vendors: {self.stats['reconciled']} | "
            f"Vendor conflicts: {len(self.vendor_conflicts)}"
        )
        print(f"  Duplicate groups: {len(self.duplicate_groups)} (HIGH: {high}, MEDIUM: {medium})")
        if self.stats["feedback_skipped"]:
            print(f"  Feedback skipped: {self.stats['feedback_skipped']} groups (user rejections)")
        print("\nReview these reports before setting DRY_RUN = False:")
        print(f"  Markdown preview: {report_paths['preview_md']}")
        print(f"  Restructure CSV:  {report_paths['preview_csv']}")
        print(f"  Duplicate CSV:    {report_paths['duplicate_csv']}")
        print(f"  Nested fixes CSV: {report_paths['nested_csv']}")
        print(f"  Coexistence CSV:  {report_paths['coexistence_csv']}")
        print(f"  Investigation CSV:{report_paths['investigation_csv']}")
        print(f"  Summary:          {report_paths['summary_txt']}")
        if report_paths.get("archive_peek_csv") and report_paths["archive_peek_csv"].exists():
            print(f"  Archive peek CSV: {report_paths['archive_peek_csv']}")
        if report_paths.get("scene_archive_peek_csv") and report_paths["scene_archive_peek_csv"].exists():
            print(f"  Scene archive CSV:{report_paths['scene_archive_peek_csv']}")
        if report_paths.get("multipart_diag_csv") and report_paths["multipart_diag_csv"].exists():
            print(f"  Multipart diag:   {report_paths['multipart_diag_csv']}")
        if report_paths.get("scene_rename_csv") and report_paths["scene_rename_csv"].exists():
            print(f"  Scene rename CSV: {report_paths['scene_rename_csv']}")
        if "share_preview_md" in report_paths:
            print(f"\n  Copies also on share: {self.root_dir / '_dedupe_reports'}")

        self.logger.info(
            "Scan complete v%s: scanned=%s cache_hits=%s routed=%s investigation=%s nested=%s dupe_groups=%s errors=%s dry_run=%s",
            ENGINE_VERSION,
            self.stats["scanned"],
            self.stats["cache_hits"],
            self.stats["routed"],
            self.stats["investigation"],
            len(self.nested_issues),
            len(self.duplicate_groups),
            self.stats["errors"],
            self.dry_run,
        )


