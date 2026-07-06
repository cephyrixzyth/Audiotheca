"""Callable MVP handlers for Audiotheca spec codes."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

from audiotheca.spec.schema import SpecEntry, get_entry

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _import_callable(dotted: str) -> Callable[..., Any]:
    module_path, _, func_name = dotted.rpartition(".")
    module = importlib.import_module(module_path)
    target = getattr(module, func_name)
    if not callable(target):
        raise TypeError(f"{dotted} is not callable")
    return target


def get_handler_info(code: str) -> dict[str, Any] | None:
    entry = get_entry(code)
    if entry is None:
        return None
    info: dict[str, Any] = entry.to_dict()
    info["invokable"] = entry.handler is not None and entry.section != "UI-LOG"
    return info


def invoke_handler(code: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = get_entry(code)
    if entry is None:
        raise KeyError(f"Unknown spec code: {code}")

    payload = payload or {}

    if entry.section == "UI-LOG":
        return {
            "code": entry.code,
            "frontend": True,
            "message": "UI spec codes are implemented in the React layer",
            "module": entry.module,
        }

    if not entry.handler:
        return {
            "code": entry.code,
            "status": entry.status,
            "message": "No invoke handler registered for this code",
            "module": entry.module,
        }

    fn = _dispatch(entry, payload)
    result = fn(**payload) if payload else fn()
    return {"code": entry.code, "status": entry.status, "result": result}


def _dispatch(entry: SpecEntry, payload: dict[str, Any]) -> Callable[..., Any]:
    code = entry.code
    handler = entry.handler
    assert handler is not None

    if code == "PTH-MSK":
        from path_mask import mask_path

        return lambda **kw: mask_path(kw.get("path", ""))

    if code == "IO-THROT":
        from scan_options import ScanOptions

        return lambda **kw: ScanOptions.from_dict(kw).to_dict()

    if code == "AUD-LOG":
        from audiotheca.transaction_ledger import list_entries

        return lambda **kw: {"entries": list_entries(limit=int(kw.get("limit", 50)))}

    if code == "REG-EMU":
        from registry_emu import get_value

        return lambda **kw: {
            "value": get_value(str(kw.get("key", kw.get("hive", ""))), str(kw.get("name", "")), str(kw.get("default", "")))
        }

    if code == "MCP-LOOP":
        from audiotheca.ai_lookup.mcp_loop import offline_lookup_item

        return lambda **kw: offline_lookup_item(kw.get("item", {}), root=kw.get("root"))

    if code == "MTRK-COLLAPSE":
        from pathlib import Path

        from multitrack_group import collapse_session_objects

        return lambda **kw: collapse_session_objects(Path(str(kw.get("path", "."))))

    if code == "CRC-DIAG":
        from pathlib import Path

        from archive_crc import diagnose_archive

        return lambda **kw: diagnose_archive(Path(str(kw.get("path", ""))))

    if code == "HASH-EXT":
        from pathlib import Path

        from hash_ext import hash_file

        return lambda **kw: hash_file(
            Path(str(kw.get("path", ""))),
            algorithms=tuple(kw.get("algorithms", ("md5", "sha256"))),
        )

    if code == "SYM-AGG":
        from sym_agg import build_virtual_tree

        return lambda **kw: build_virtual_tree(dict(kw.get("mappings", {})))

    if code == "MMAP-ENG":
        from mmap_eng import list_tree_preview

        return lambda **kw: list_tree_preview(
            str(kw.get("root", ".")),
            limit=int(kw.get("limit", 200)),
            max_depth=int(kw.get("max_depth", 3)),
        )

    if code == "CARVE-STR":
        from carve_str import carve_strings

        return lambda **kw: carve_strings(str(kw.get("path", "")), limit=int(kw.get("limit", 200)))

    if code == "ARCH-ALRT":
        from version_verify import architecture_warning

        return lambda **kw: architecture_warning(str(kw.get("install_path", "")))

    if code == "XFER-BNDL":
        from xfer_bndl import export_bundle, export_workspace_bundle

        if payload.get("workspace"):
            return lambda **kw: export_workspace_bundle(
                str(kw.get("output", "audiotheca_bundle.zip")),
                home=kw.get("home"),
            )
        return lambda **kw: export_bundle(
            str(kw.get("output", "bundle.zip")),
            manifest=kw.get("manifest"),
            files=list(kw.get("files", [])),
        )

    if code == "NET-SAFE":
        from net_safe import set_paused, status

        if "paused" in payload:
            return lambda **kw: set_paused(bool(kw["paused"]))
        return status

    if code == "ACU-DEDUP":
        from reference_dedupe_engine import find_acoustic_duplicates

        return lambda **kw: find_acoustic_duplicates(list(kw.get("paths", [])))

    if code == "PHN-SPEECH":
        from phn_speech import search_transcript

        return lambda **kw: search_transcript(str(kw.get("text", "")), str(kw.get("query", "")))

    if code == "CLD-CACHE":
        from cld_cache import cache_status

        return cache_status

    if code == "S3-CONN":
        from s3_conn import s3_status

        return s3_status

    if code == "ANTI-PHONE":
        from anti_phone import generate_hosts_block

        return lambda **kw: generate_hosts_block(
            list(kw.get("domains") or []) or None,
            vendors=list(kw.get("vendors") or []) or None,
        )

    if code == "QRNT-RPR":
        from qrnt_rpr import analyze_quarantine

        return lambda **kw: analyze_quarantine(str(kw.get("path", "")), root=kw.get("root"))

    if code == "EXE-INTRCPT":
        from exe_intrcpt import evaluate_execution

        return lambda **kw: evaluate_execution(str(kw.get("path", "")), action=str(kw.get("action", "launch")))

    if code == "SHRED-ERASE":
        from pathlib import Path

        from shred_erase import secure_delete

        return lambda **kw: secure_delete(Path(str(kw.get("path", ""))), passes=int(kw.get("passes", 3)))

    if code == "ENV-YAML":
        from audiotheca.environment import export_blueprint_yaml

        return export_blueprint_yaml

    if code == "STG-ISOL":
        from scan_options import validate_staging_root

        return lambda **kw: validate_staging_root(str(kw.get("path") or kw.get("staging_root") or ""))

    if code == "NODE-SYNC":
        from node_sync import compare_peer_manifest, sync_status

        if "manifest" in payload:
            return lambda **kw: compare_peer_manifest(dict(kw.get("manifest") or {}))
        return lambda **kw: sync_status(node_id=str(kw.get("node_id", "local")))

    if code == "BTQ-FPT":
        from btq_fpt import match_boutique

        return lambda **kw: match_boutique(str(kw.get("path") or kw.get("name") or ""))

    if code == "WEB-SPDR":
        from web_spdr import plan_lookup

        return lambda **kw: plan_lookup(str(kw.get("query", "")), preset=kw.get("preset"))

    if code == "TAG-GEN":
        from tag_gen import generate_tags

        return lambda **kw: generate_tags(str(kw.get("text", "")), max_tags=int(kw.get("max_tags", 12)))

    if code == "NFO-PARSE":
        from audiotheca.ai_lookup.nfo_reader import parse_nfo_file, parse_release_text

        if payload.get("path"):
            return lambda **kw: parse_nfo_file(str(kw.get("path", "")))
        return lambda **kw: {"parsed": parse_release_text(str(kw.get("text", ""))), "path": None}

    if code == "TLM-PERF":
        from system_metrics import get_metrics_history

        return lambda **kw: get_metrics_history(limit=int(kw.get("limit", 60)))

    if code == "BWF-EXT" or code == "SFX-MAP":
        from pathlib import Path

        from bwf_metadata import parse_wav_metadata

        return lambda **kw: parse_wav_metadata(Path(str(kw.get("path", ""))))

    if code == "NST-ARC":
        from pathlib import Path

        from archive_nest import index_nested_archives

        return lambda **kw: index_nested_archives(
            Path(str(kw.get("path", ""))),
            depth=int(kw.get("depth", 2)),
            limit=int(kw.get("limit", 50)),
        )

    if code == "SCN-CLS":
        from archive_peek import classify_peek

        names = payload.get("sample_names") or payload.get("names") or []
        return lambda **kw: {
            "classification": classify_peek(
                str(kw.get("folder_name", "")),
                list(kw.get("sample_names") or kw.get("names") or names),
                kw.get("error"),
            )
        }

    if code == "CONF-CAT":
        from audiotheca.verification import confidence_category

        return lambda **kw: confidence_category(
            str(kw.get("id_confidence", kw.get("confidence", "UNKNOWN"))),
            str(kw.get("id_method", "")),
        )

    if code == "STRIP-DATA":
        from audiotheca.ai_lookup.telemetry import anonymization_status

        return lambda **kw: anonymization_status(dict(kw.get("item") or kw))

    if code == "VNDR-LNK":
        from installation_registry import vendor_links

        return lambda **kw: vendor_links(str(kw.get("product_key", "")))

    if code == "DEP-EXT":
        from pathlib import Path

        from session_parse import parse_session

        return lambda **kw: parse_session(Path(str(kw.get("path", ""))))

    if code == "DAW-SIDE":
        from daw_side import write_blueprint

        return lambda **kw: write_blueprint(home=kw.get("home"))

    if code == "DRV-COOLDWN":
        from drv_cooldwn import apply_cooldown_before_scan, queue_scan_request, queue_status

        if payload.get("status"):
            return lambda **_kw: queue_status()
        if payload.get("root"):
            return lambda **kw: apply_cooldown_before_scan(
                root=str(kw.get("root", "")),
                cooldown_s=kw.get("cooldown_s"),
            )
        return lambda **kw: queue_scan_request(dict(kw.get("request") or kw))

    if code == "PKG-HRVST":
        from pkg_hrvst import inspect_installer

        return lambda **kw: inspect_installer(str(kw.get("path", "")))

    if code == "PROP-INJ":
        from prop_inj import inject_properties, read_properties

        if payload.get("read"):
            return lambda **kw: read_properties(str(kw.get("path", "")))
        return lambda **kw: inject_properties(
            str(kw.get("path", "")),
            tags={str(k): str(v) for k, v in dict(kw.get("tags") or {}).items()},
        )

    if code == "TAG-PROP":
        from tag_prop import propagate_tags

        return lambda **kw: propagate_tags(
            list(kw.get("paths") or []),
            {str(k): str(v) for k, v in dict(kw.get("tags") or {}).items()},
            dry_run=bool(kw.get("dry_run", False)),
        )

    if code == "WAV-CCH":
        from pathlib import Path

        from wav_cch import waveform_cache_key

        return lambda **kw: waveform_cache_key(
            Path(str(kw.get("path", ""))),
            bins=int(kw.get("bins", 64)),
            refresh=bool(kw.get("refresh", False)),
        )

    if code == "SIL-TRUNC":
        from sil_trunc import analyze_silence

        return lambda **kw: analyze_silence(path=kw.get("path"))

    if code == "LUFS-NORM":
        from lufs_norm import normalize_loudness

        return lambda **kw: normalize_loudness(
            target_lufs=float(kw.get("target_lufs", -23.0)),
            measured_lufs=kw.get("measured_lufs"),
        )

    if code == "BPM-DET":
        from pathlib import Path

        from bpm_det import detect_bpm

        return lambda **kw: detect_bpm(
            str(kw.get("name", "")),
            path=Path(str(kw["path"])) if kw.get("path") else None,
        )

    if code == "K-DET":
        from k_det import detect_key

        return lambda **kw: detect_key(str(kw.get("name", "")))

    if code == "V-MATX":
        from v_matx import build_version_matrix

        return lambda **kw: build_version_matrix(formats=tuple(kw.get("formats", ("vst3", "aax", "au", "clap"))))

    if code == "DAW-VAL":
        from daw_val import validate_plugin

        return lambda **kw: validate_plugin(str(kw.get("path", "")))

    if code == "ML-SIM":
        from ml_sim import classify_spectral

        return lambda **kw: classify_spectral(str(kw.get("name", "")), wav_info=kw.get("wav_info"))

    if code == "SIG-CAP":
        from sig_cap import capture_status

        return lambda **kw: capture_status(
            channels=int(kw.get("channels", 2)),
            sample_rate=int(kw.get("sample_rate", 48000)),
        )

    if code == "SURR-DMUX":
        from pathlib import Path

        from surround_demux import detect_surround_layout

        return lambda **kw: detect_surround_layout(
            Path(str(kw.get("path", ""))) if kw.get("path") else None,
            wav_info=kw.get("wav_info"),
        )

    if code == "CLN-SWEEP":
        from cln_sweep import scan_orphans

        return lambda **kw: scan_orphans(
            str(kw.get("root", ".")),
            patterns=tuple(kw.get("patterns") or ()) or None,
            limit=int(kw.get("limit", 200)),
        )

    if code == "DIST-SCAN":
        from dist_scan import assign_worker, shard_paths

        workers = [str(w) for w in (payload.get("workers") or []) if w]
        paths = payload.get("paths")
        if isinstance(paths, list) and paths:
            return lambda **kw: shard_paths([str(p) for p in paths], workers)
        return lambda **kw: assign_worker(workers, shard=int(kw.get("shard", 0)))

    if code == "STRG-TIER":
        from strg_tier import recommend_tier

        return lambda **kw: recommend_tier(
            path=str(kw["path"]) if kw.get("path") else None,
            age_days=kw.get("age_days"),
            access_count=int(kw.get("access_count", 0)),
            size_gb=kw.get("size_gb"),
        )

    if code == "PATH-RLOC":
        from path_rloc import translate_batch, translate_path

        paths = payload.get("paths")
        if paths:
            return lambda **kw: translate_batch(
                [str(p) for p in paths],
                target_os=str(kw.get("target_os", "mac")),
                custom_map=kw.get("custom_map"),
            )
        return lambda **kw: translate_path(
            str(kw.get("path", "")),
            target_os=str(kw.get("target_os", "mac")),
            custom_map=kw.get("custom_map"),
        )

    if code == "CUE-LOG":
        from cue_log import export_cue

        return lambda **kw: export_cue(
            list(kw.get("markers") or []),
            format=str(kw.get("format", "csv")),
            fps=float(kw.get("fps", 24.0)),
            title=str(kw.get("title", "Audiotheca Cue Log")),
        )

    if code == "SEMVER-SCN":
        from version_verify import check_installation

        return lambda **kw: check_installation(
            str(kw.get("install_path", "")),
            expected_version=str(kw.get("expected_version", "")),
        )

    if code == "ASYM-UPD":
        from version_verify import load_manifest

        return load_manifest

    if code == "MEM-SCAN":
        from mem_scan import scan_process

        return lambda **kw: scan_process(int(kw.get("pid", 0)))

    if code == "ISO-ENV":
        from audiotheca.environment import probe_environment

        return probe_environment

    if code == "DKR-TUN":
        from dkr_tun import gluetun_config

        return gluetun_config

    if code == "PTH-NRM":
        from pth_nrm import path_info

        return lambda **kw: path_info(str(kw.get("path", "")))

    return _import_callable(handler)
