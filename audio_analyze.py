"""Combined audio forensics pipeline for WAV assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audio_wave import measure_integrated_loudness_db, read_wav_info
from audiotheca.audio_tags import read_audio_tags
from bwf_metadata import parse_wav_metadata
from bpm_det import detect_bpm
from k_det import detect_key
from lufs_norm import normalize_loudness
from ml_sim import classify_spectral
from sil_trunc import analyze_silence
from surround_demux import detect_surround_layout
from ucs_map import parse_ucs_filename
from wav_cch import waveform_cache_key


def analyze_audio_file(path: str | Path, *, target_lufs: float = -23.0) -> dict[str, Any]:
    target = Path(path)
    name = target.name
    info = read_wav_info(target)
    if not info.get("ok"):
        return {"path": str(target), "ok": False, "error": info.get("error")}

    tags = read_audio_tags(target)
    tag_payload = tags.get("tags") if tags.get("ok") else {}
    tag_bpm = tag_payload.get("bpm") if isinstance(tag_payload, dict) else None
    tag_key = tag_payload.get("key") if isinstance(tag_payload, dict) else None
    tag_mode = tag_payload.get("mode") if isinstance(tag_payload, dict) else None

    loudness = measure_integrated_loudness_db(target)
    lufs = normalize_loudness(
        target_lufs=target_lufs,
        measured_lufs=loudness.get("measured_lufs"),
        engine=loudness.get("engine"),
        standard=loudness.get("standard"),
    )

    bwf = parse_wav_metadata(target)
    return {
        "path": str(target),
        "ok": True,
        "info": info,
        "waveform": waveform_cache_key(target, bins=32),
        "loudness": loudness,
        "lufs_norm": lufs,
        "bpm": detect_bpm(name, path=target, tag_bpm=tag_bpm if isinstance(tag_bpm, (int, float)) else None),
        "key": detect_key(
            name,
            tag_key=str(tag_key) if tag_key else None,
            tag_mode=str(tag_mode) if tag_mode else None,
        ),
        "tags": tags,
        "ucs": parse_ucs_filename(name),
        "spectral": classify_spectral(name, wav_info=info),
        "surround": detect_surround_layout(target, wav_info=info),
        "silence": analyze_silence(path=target),
        "bwf": {
            "chunks": bwf.get("chunks", []),
            "vendor_hints": bwf.get("vendor_hints", []),
            "bext": bwf.get("bext", {}),
            "axml": bwf.get("axml"),
            "ixml": bwf.get("ixml"),
        },
        "sfx_map": {
            "vendor_hints": bwf.get("vendor_hints", []),
            "chunks": bwf.get("chunks", []),
        },
    }
