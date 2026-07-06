"""Audiotheca architecture spec registry — 94 codes across 5 sections."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

SpecStatus = Literal["done", "partial", "mvp"]


@dataclass(frozen=True)
class SpecEntry:
    code: str
    section: str
    title: str
    description: str
    status: SpecStatus
    module: str
    handler: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def _e(
    code: str,
    section: str,
    title: str,
    description: str,
    status: SpecStatus,
    module: str,
    handler: str | None = None,
) -> SpecEntry:
    return SpecEntry(code, section, title, description, status, module, handler)


SPEC_ENTRIES: tuple[SpecEntry, ...] = (
    # ── SYS-ING (16) ──
    _e("ISO-ENV", "SYS-ING", "Isolated engine environment", "Local site-packages loop before global imports", "done", "audiotheca/environment.py", "audiotheca.environment.probe_environment"),
    _e("NAT-BIN", "SYS-ING", "Native binaries", "Tauri + PyInstaller sidecars for Win/macOS/Linux", "done", "scripts/build_sidecars.py"),
    _e("DKR-TUN", "SYS-ING", "Docker VPN sidecar", "Gluetun compose profile and live compose probe", "done", "dkr_tun.py", "dkr_tun.gluetun_config"),
    _e("PTH-MSK", "SYS-ING", "Path masking", "Template user path redaction for logs and API", "done", "path_mask.py", "path_mask.mask_path"),
    _e("SYN-GEN", "SYS-ING", "Synthetic demo assets", "Mock library and seeded reports for walkthroughs", "done", "docs/demo"),
    _e("AIR-GAP", "SYS-ING", "Air-gap runtime", "Block outbound telemetry and remote sync", "done", "runtime_policy.py", "runtime_policy.runtime_flags"),
    _e("TLM-PERF", "SYS-ING", "Host telemetry", "CPU, RAM, disk IOPS, thread count", "done", "system_metrics.py", "system_metrics.collect_metrics"),
    _e("TLM-STRG", "SYS-ING", "NAS storage telemetry", "Network mount latency and dual metrics", "done", "system_metrics.py", "system_metrics.collect_dual_metrics"),
    _e("AUD-LOG", "SYS-ING", "Audit transaction ledger", "Immutable move/quarantine/override log", "done", "audiotheca/transaction_ledger.py", "audiotheca.transaction_ledger.list_entries"),
    _e("IO-THROT", "SYS-ING", "Scan I/O throttle", "Background scan worker and delay limits", "done", "scan_options.py", "scan_options.ScanOptions.from_dict"),
    _e("MNT-LSTN", "SYS-ING", "Library mount watcher", "Hot-swap and filesystem change listener", "done", "audiotheca/watcher.py"),
    _e("CTX-PROF", "SYS-ING", "Admin permission profile", "Elevation check for destructive operations", "done", "ctx_prof.py", "ctx_prof.check_admin_permissions"),
    _e("SYM-AGG", "SYS-ING", "Virtual path aggregation", "Unified directory tree with persisted mappings", "done", "sym_agg.py", "sym_agg.build_virtual_tree"),
    _e("PTH-NRM", "SYS-ING", "Long path normalization", "Windows extended-length path prefix and safe open", "done", "pth_nrm.py", "pth_nrm.path_info"),
    _e("MMAP-ENG", "SYS-ING", "Lazy tree mapper", "Instant browse via scandir lazy iterator", "done", "mmap_eng.py", "mmap_eng.list_tree_preview"),
    _e("DRV-COOLDWN", "SYS-ING", "Drive spin-up cooldown", "Scan request queue wired to job runner", "done", "drv_cooldwn.py", "drv_cooldwn.queue_scan_request"),
    # ── AUD-PIP (25) ──
    _e("BWF-EXT", "AUD-PIP", "BWF metadata extract", "axml, bext, iXML header parsing", "done", "bwf_metadata.py", "bwf_metadata.parse_wav_metadata"),
    _e("MTRK-COLLAPSE", "AUD-PIP", "Multitrack collapse", "Stem/session object grouping", "done", "multitrack_group.py", "multitrack_group.collapse_session_objects"),
    _e("NST-ARC", "AUD-PIP", "Nested archive index", "In-memory layered archive listing", "done", "archive_nest.py", "archive_nest.index_nested_archives"),
    _e("SCN-CLS", "AUD-PIP", "Scene class scanner", "Release group footprint heuristics", "done", "archive_peek.py", "archive_peek.classify_peek"),
    _e("BTQ-FPT", "AUD-PIP", "Boutique fingerprints", "Independent developer auth pattern matching", "done", "btq_fpt.py", "btq_fpt.match_boutique"),
    _e("SFX-MAP", "AUD-PIP", "Studio BWF map", "Major sound library signature hints", "done", "bwf_metadata.py", "bwf_metadata.parse_wav_metadata"),
    _e("ML-SIM", "AUD-PIP", "Spectral classifier", "Sonic category heuristics from name and WAV metadata", "done", "ml_sim.py", "ml_sim.classify_spectral"),
    _e("ACU-DEDUP", "AUD-PIP", "Acoustic dedupe", "Content-hash duplicate detection", "done", "reference_dedupe_engine.py"),
    _e("SIG-CAP", "AUD-PIP", "Signal capture", "Audio input device discovery bridge", "done", "sig_cap.py", "sig_cap.capture_status"),
    _e("SURR-DMUX", "AUD-PIP", "Surround demux", "5.1/7.1 layout from channel count and filename", "done", "surround_demux.py", "surround_demux.detect_surround_layout"),
    _e("WAV-CCH", "AUD-PIP", "Waveform cache", "Micro-waveform peak cache for preview UI", "done", "wav_cch.py", "wav_cch.waveform_cache_key"),
    _e("PHN-SPEECH", "AUD-PIP", "Phonetic search", "Offline dialogue term and phonetic search", "done", "phn_speech.py", "phn_speech.search_transcript"),
    _e("PKG-HRVST", "AUD-PIP", "Installer harvest", "MSI/EXE/PKG payload inspect and carve", "done", "pkg_hrvst.py", "pkg_hrvst.inspect_installer"),
    _e("DAW-VAL", "AUD-PIP", "Plugin validator", "VST3/AAX/AU bundle structure validation", "done", "daw_val.py", "daw_val.validate_plugin"),
    _e("DRP-ZONE", "AUD-PIP", "Drag-drop targets", "Cross-UI drop framework", "done", "ui/src/components"),
    _e("CARVE-STR", "AUD-PIP", "Binary string carve", "Extract URLs and version tokens from binaries", "done", "carve_str.py", "carve_str.carve_strings"),
    _e("CRC-DIAG", "AUD-PIP", "Archive CRC diagnose", "Zip/RAR/7z structural integrity check", "done", "archive_crc.py", "archive_crc.diagnose_archive"),
    _e("HASH-EXT", "AUD-PIP", "Multi-hash verify", "MD5/SHA-256 file hashing", "done", "hash_ext.py", "hash_ext.hash_file"),
    _e("PROP-INJ", "AUD-PIP", "Property injection", "Sidecar .audiotheca.json tag metadata", "done", "prop_inj.py", "prop_inj.inject_properties"),
    _e("UCS-MAP", "AUD-PIP", "UCS filename map", "Universal Category System alignment with labels", "done", "ucs_map.py", "ucs_map.parse_ucs_filename"),
    _e("SIL-TRUNC", "AUD-PIP", "Silence trim", "Leading/trailing silence analysis on WAV files", "done", "sil_trunc.py", "sil_trunc.analyze_silence"),
    _e("LUFS-NORM", "AUD-PIP", "LUFS normalize", "Integrated loudness measurement and gain suggestion", "done", "lufs_norm.py", "lufs_norm.normalize_loudness"),
    _e("BPM-DET", "AUD-PIP", "BPM detection", "Tempo from filename and duration heuristics", "done", "bpm_det.py", "bpm_det.detect_bpm"),
    _e("K-DET", "AUD-PIP", "Key detection", "Root pitch from filename patterns", "done", "k_det.py", "k_det.detect_key"),
    _e("V-MATX", "AUD-PIP", "Plugin version matrix", "VST3/AAX/AU/CLAP install matrix from registry", "done", "v_matx.py", "v_matx.build_version_matrix"),
    # ── AI-SEC (14) ──
    _e("MCP-LOOP", "AI-SEC", "MCP lookup loop", "Offline/online hybrid AI disambiguation", "done", "audiotheca/ai_lookup/mcp_loop.py", "audiotheca.ai_lookup.mcp_loop.offline_lookup_item"),
    _e("WEB-SPDR", "AI-SEC", "Web spider agent", "SearXNG-backed wiki/scene lookup", "done", "web_spdr.py", "web_spdr.plan_lookup"),
    _e("TAG-GEN", "AI-SEC", "AI tag generator", "NFO and release text tag extraction", "done", "tag_gen.py", "tag_gen.generate_tags"),
    _e("NFO-PARSE", "AI-SEC", "NFO/readme parse", "Release detail text ingestion", "done", "audiotheca/ai_lookup/nfo_reader.py", "audiotheca.ai_lookup.nfo_reader.parse_release_text"),
    _e("CONF-CAT", "AI-SEC", "Confidence category", "Pending verification tier tagging", "done", "audiotheca/verification.py", "audiotheca.verification.confidence_category"),
    _e("STRIP-DATA", "AI-SEC", "Data anonymization", "Strip PII before external AI calls", "done", "audiotheca/ai_lookup/telemetry.py", "audiotheca.ai_lookup.telemetry.anonymization_status"),
    _e("LKP-CACHE", "AI-SEC", "Lookup cache", "Local metadata match cache", "done", "audiotheca/ai_lookup/cache.py"),
    _e("MAL-QRNT", "AI-SEC", "Malware quarantine", "Flagged payload isolation", "done", "malware_scanner.py"),
    _e("QRNT-RPR", "AI-SEC", "Quarantine repair", "Malicious block repair analysis via heuristics", "done", "qrnt_rpr.py", "qrnt_rpr.analyze_quarantine"),
    _e("EXE-INTRCPT", "AI-SEC", "Execution interceptor", "Block unauthorized launch policy engine", "done", "exe_intrcpt.py", "exe_intrcpt.evaluate_execution"),
    _e("SHRED-ERASE", "AI-SEC", "Secure erase", "Multi-pass permanent file destruction", "done", "shred_erase.py", "shred_erase.secure_delete"),
    _e("REG-EMU", "AI-SEC", "Registry emulator", "Isolated registry redirect store", "done", "registry_emu.py", "registry_emu.get_value"),
    _e("MEM-SCAN", "AI-SEC", "Memory scan", "Process allocation inspection via psutil", "done", "mem_scan.py", "mem_scan.scan_process"),
    _e("ANTI-PHONE", "AI-SEC", "Phone-home block", "Hosts file generator with vendor domains", "done", "anti_phone.py", "anti_phone.generate_hosts_block"),
    # ── LFC-ORCH (18) ──
    _e("SEMVER-SCN", "LFC-ORCH", "Semver scanner", "PE/plist version attribute read", "done", "version_verify.py", "version_verify.check_installation"),
    _e("ASYM-UPD", "LFC-ORCH", "Asymmetric update check", "Manifest compare without host disclosure", "done", "version_verify.py", "version_verify.load_manifest"),
    _e("VNDR-LNK", "LFC-ORCH", "Vendor links", "Product page and docs URLs in registry", "done", "installation_registry.py", "installation_registry.vendor_links"),
    _e("ARCH-ALRT", "LFC-ORCH", "Architecture alert", "Legacy Intel/Rosetta/ARM translation warnings", "done", "version_verify.py", "version_verify.architecture_warning"),
    _e("DEP-EXT", "LFC-ORCH", "Dependency extract", "Session file missing asset catalog", "done", "session_parse.py", "session_parse.parse_session"),
    _e("CLN-SWEEP", "LFC-ORCH", "Cleanup sweeper", "Orphaned sidecar and junk file scan", "done", "cln_sweep.py", "cln_sweep.scan_orphans"),
    _e("ENV-YAML", "LFC-ORCH", "Environment YAML", "Multi-machine config blueprint export", "done", "audiotheca/environment.py", "audiotheca.environment.export_blueprint_yaml"),
    _e("STG-ISOL", "LFC-ORCH", "Staging isolation", "Alternate staging root for trials", "done", "scan_options.py", "scan_options.validate_staging_root"),
    _e("NODE-SYNC", "LFC-ORCH", "Node sync", "Multi-workstation peer sync manifest", "done", "node_sync.py", "node_sync.sync_status"),
    _e("DIST-SCAN", "LFC-ORCH", "Distributed scan", "Network worker hash shard assignment", "done", "dist_scan.py", "dist_scan.assign_worker"),
    _e("CLD-CACHE", "LFC-ORCH", "Cloud cache", "Dropbox/Drive metadata cache on disk", "done", "cld_cache.py", "cld_cache.cache_entry"),
    _e("STRG-TIER", "LFC-ORCH", "Storage tiering", "Hot/cold migration from mtime and size", "done", "strg_tier.py", "strg_tier.recommend_tier"),
    _e("S3-CONN", "LFC-ORCH", "S3 connector", "Object storage bucket list via boto3", "done", "s3_conn.py", "s3_conn.connect_bucket"),
    _e("NET-SAFE", "LFC-ORCH", "Network safe pause", "Pause/resume on link interruption", "done", "net_safe.py", "net_safe.status"),
    _e("XFER-BNDL", "LFC-ORCH", "Transfer bundle", "Self-contained workspace deployment zip export", "done", "xfer_bndl.py", "xfer_bndl.export_workspace_bundle"),
    _e("PATH-RLOC", "LFC-ORCH", "Path relocation", "Win/mac project path translation with custom maps", "done", "path_rloc.py", "path_rloc.translate_path"),
    _e("CUE-LOG", "LFC-ORCH", "Cue log export", "Preview timestamp EDL/CSV export", "done", "cue_log.py", "cue_log.export_cue"),
    _e("DAW-SIDE", "LFC-ORCH", "DAW sidecar plugin", "Plugin manifest and JUCE blueprint export", "done", "daw_side.py", "daw_side.write_blueprint"),
    # ── UI-LOG (21) ──
    _e("CANVAS-DRG", "UI-LOG", "Canvas drag layout", "Free-form dashboard widget blocks", "done", "ui/src/components/ReorderableSections.tsx"),
    _e("REFLOW-DYN", "UI-LOG", "Dynamic reflow", "Dense grid reflow when sections toggle", "done", "ui/src/components/DashboardHome.tsx"),
    _e("AXIS-RESIZE", "UI-LOG", "Axis resize", "Canvas widget col/row span resize handles", "done", "ui/src/components/ReorderableSections.tsx"),
    _e("CLR-CLUS", "UI-LOG", "Clear placeholders", "Hide empty canvas gap cells until drag", "done", "ui/src/components/ReorderableSections.tsx"),
    _e("LBL-STD", "UI-LOG", "Label standard", "Unified phase and loop marker labels", "done", "ui/src/utils/scanDisplay.ts"),
    _e("ICON-BTN", "UI-LOG", "Icon buttons", "Minimal icon-only controls with focus", "done", "ui/src/App.css"),
    _e("HVR-HL", "UI-LOG", "Hover highlight", "Global low-latency hover states on controls", "done", "ui/src/App.css"),
    _e("WYSIWYG-THM", "UI-LOG", "Theme studio", "Visual contrast and accent customizer", "done", "ui/src/components/ThemeSwitcher.tsx"),
    _e("LOG-FIXED", "UI-LOG", "Fixed log height", "Internal scroll log wrapper", "done", "ui/src/components/ScanPanel.tsx"),
    _e("PHS-IND", "UI-LOG", "Phase indicators", "Active micro-phase loading animations", "done", "ui/src/components/PhaseProgressBar.tsx"),
    _e("LOG-FLTR", "UI-LOG", "Log level filter", "ALL/ERROR/WARNING/SCANNER toggles", "done", "ui/src/components/ScanPanel.tsx"),
    _e("LOG-SRCH", "UI-LOG", "Log search", "Live console line search", "done", "ui/src/components/ScanPanel.tsx"),
    _e("ETA-HUM", "UI-LOG", "Human ETA", "Duration formatting as 1h 23m 32s", "done", "ui/src/utils/scanDisplay.ts"),
    _e("MIX-MATX", "UI-LOG", "Output mixer matrix", "Multi-channel preview routing controls", "done", "ui/src/components/PreviewSessionPanel.tsx"),
    _e("WAV-TRIM", "UI-LOG", "Waveform trimmer", "In-UI non-destructive boundary trim", "done", "ui/src/components/AudioPreviewStrip.tsx"),
    _e("TMP-SYNC", "UI-LOG", "Tempo sync", "Preview BPM match to DAW project", "done", "ui/src/hooks/usePreviewSession.ts"),
    _e("KEY-PITCH", "UI-LOG", "Key pitch shift", "Real-time transposition during audition", "done", "ui/src/hooks/usePreviewSession.ts"),
    _e("AUTO-AUD", "UI-LOG", "Auto audition", "Playback on row focus/hover", "done", "ui/src/components/AudioPreviewStrip.tsx"),
    _e("BPRNT-SAVE", "UI-LOG", "Layout blueprint", "Save/load grid coordinate presets", "done", "ui/src/hooks/useLayoutPresets.ts"),
    _e("LOG-DEDUP", "UI-LOG", "Log deduplication", "Drop duplicate progress strings", "done", "ui/src/utils/scanDisplay.ts"),
    _e("TAG-PROP", "UI-LOG", "Tag propagation", "Background meta-tag batch sidecar writes", "done", "tag_prop.py", "tag_prop.propagate_tags"),
)

SPEC_BY_CODE: dict[str, SpecEntry] = {entry.code: entry for entry in SPEC_ENTRIES}


def list_entries(*, section: str | None = None) -> list[dict[str, str | None]]:
    rows = SPEC_ENTRIES if section is None else [e for e in SPEC_ENTRIES if e.section == section]
    return [entry.to_dict() for entry in rows]


def get_entry(code: str) -> SpecEntry | None:
    return SPEC_BY_CODE.get(code.upper())


def catalog_summary() -> dict[str, int | dict[str, int]]:
    by_status: dict[str, int] = {"done": 0, "partial": 0, "mvp": 0}
    by_section: dict[str, int] = {}
    for entry in SPEC_ENTRIES:
        by_status[entry.status] = by_status.get(entry.status, 0) + 1
        by_section[entry.section] = by_section.get(entry.section, 0) + 1
    return {
        "total": len(SPEC_ENTRIES),
        "by_status": by_status,
        "by_section": by_section,
    }
