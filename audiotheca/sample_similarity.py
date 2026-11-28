"""Sample similarity finder — "more like this" for one-shots and loops.

Each sample is reduced to a small timbre vector computed locally with numpy:

  * the spectral envelope (32 log-spaced bands, 40 Hz to 16 kHz), level-normalized
    so a quiet and a loud kick compare as kicks
  * how much each band moves over time
  * brightness, noisiness, roll-off, zero crossings, onset density,
    attack position, decay and length

Vectors are z-scored across the index and compared with cosine similarity.
Nothing leaves the machine and no model download is needed.

A learned audio embedding can be added through an extension that defines
``embed_audio(path) -> list[float]`` (for example a CLAP model the user
installs). When one is loaded its vectors are stored beside the built-in
features and used for ranking instead.

WAV (PCM 8/16/24/32-bit and 32/64-bit float, WAVE_FORMAT_EXTENSIBLE) and AIFF
/ AIFF-C (uncompressed) are decoded natively. FLAC, MP3, OGG and M4A are used
when ``soundfile`` is installed; otherwise they are listed as skipped.
"""

from __future__ import annotations

import json
import os
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from api.paths import report_dir
from audiotheca.local_storage import locked, write_json

INDEX_PATH = report_dir() / "sample_similarity_index.json"
NATIVE_EXTS = {".wav", ".wave", ".aif", ".aiff", ".aifc"}
OPTIONAL_EXTS = {".flac", ".mp3", ".ogg", ".m4a"}
FEATURE_VERSION = 1
N_BANDS = 32
ANALYSIS_SECONDS = 30.0
TARGET_RATE = 22050
FRAME = 1024
HOP = 512
MIN_SECONDS = 0.02
_MAX_FILE_BYTES = 1024 * 1024 * 1024
_SKIP_DIRS = {".git", "__macosx", "$recycle.bin", "system volume information", ".trash", ".trashes"}

FEATURE_NAMES = (
    [f"band_{i}" for i in range(N_BANDS)]
    + [f"band_motion_{i}" for i in range(N_BANDS)]
    + ["centroid", "centroid_spread", "rolloff", "flatness", "zcr", "onset_rate", "attack_pos",
       "decay", "log_duration", "crest"]
)
# Spectral shape dominates; the scalar descriptors break ties between similar envelopes.
_WEIGHTS = [1.0] * N_BANDS + [0.5] * N_BANDS + [1.5, 0.7, 1.0, 1.2, 0.8, 1.0, 0.8, 1.0, 1.5, 0.6]


class DecodeError(ValueError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- decoding


def _pcm_to_float(raw: bytes, width: int, fmt: str, big_endian: bool):
    import numpy as np

    order = ">" if big_endian else "<"
    if fmt == "float":
        if width not in (4, 8):
            raise DecodeError(f"unsupported float width {width}")
        return np.frombuffer(raw[: len(raw) - len(raw) % width], dtype=f"{order}f{width}").astype(np.float32)
    if width == 1:
        data = np.frombuffer(raw, dtype=np.uint8 if not big_endian else np.int8).astype(np.float32)
        return (data - 128.0) / 128.0 if not big_endian else data / 128.0
    if width == 2:
        return np.frombuffer(raw[: len(raw) - len(raw) % 2], dtype=f"{order}i2").astype(np.float32) / 32768.0
    if width == 3:
        usable = len(raw) - len(raw) % 3
        b = np.frombuffer(raw[:usable], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        if big_endian:
            b = b[:, ::-1]
        ints = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        ints = np.where(ints & 0x800000, ints - 0x1000000, ints)
        return ints.astype(np.float32) / 8388608.0
    if width == 4:
        return np.frombuffer(raw[: len(raw) - len(raw) % 4], dtype=f"{order}i4").astype(np.float32) / 2147483648.0
    raise DecodeError(f"unsupported sample width {width}")


def _read_wav(path: Path, max_seconds: float):
    with path.open("rb") as fh:
        head = fh.read(12)
        if len(head) < 12 or head[:4] not in (b"RIFF", b"RF64") or head[8:12] != b"WAVE":
            raise DecodeError("not a RIFF/WAVE file")
        fmt_tag = channels = rate = width = 0
        while True:
            chunk = fh.read(8)
            if len(chunk) < 8:
                raise DecodeError("no data chunk")
            cid, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
            if cid == b"fmt ":
                body = fh.read(size + (size & 1))
                fmt_tag, channels, rate = struct.unpack_from("<HHI", body, 0)
                width = struct.unpack_from("<H", body, 14)[0] // 8
                if fmt_tag == 0xFFFE and len(body) >= 26:
                    fmt_tag = struct.unpack_from("<H", body, 24)[0]
            elif cid == b"data":
                if not rate or not channels or not width:
                    raise DecodeError("data before fmt chunk")
                if size in (0, 0xFFFFFFFF):  # RF64 / streaming writers
                    size = _MAX_FILE_BYTES
                frame_bytes = channels * width
                want = min(size, int(max_seconds * rate) * frame_bytes)
                raw = fh.read(want - want % frame_bytes)
                break
            else:
                fh.seek(size + (size & 1), os.SEEK_CUR)
    if fmt_tag not in (1, 3):
        raise DecodeError(f"compressed WAV (format {fmt_tag}) is not supported")
    data = _pcm_to_float(raw, width, "float" if fmt_tag == 3 else "int", big_endian=False)
    return data.reshape(-1, channels).mean(axis=1), rate


def _ieee_extended(b: bytes) -> float:
    exponent = ((b[0] & 0x7F) << 8) | b[1]
    mantissa = int.from_bytes(b[2:10], "big")
    if exponent == 0 and mantissa == 0:
        return 0.0
    value = mantissa * 2.0 ** (exponent - 16383 - 63)
    return -value if b[0] & 0x80 else value


def _read_aiff(path: Path, max_seconds: float):
    with path.open("rb") as fh:
        head = fh.read(12)
        if len(head) < 12 or head[:4] != b"FORM" or head[8:12] not in (b"AIFF", b"AIFC"):
            raise DecodeError("not an AIFF file")
        compressed = head[8:12] == b"AIFC"
        channels = width = 0
        rate = 0.0
        kind = "int"
        big_endian = True
        while True:
            chunk = fh.read(8)
            if len(chunk) < 8:
                raise DecodeError("no SSND chunk")
            cid, size = chunk[:4], struct.unpack(">I", chunk[4:])[0]
            if cid == b"COMM":
                body = fh.read(size + (size & 1))
                channels, _frames, bits = struct.unpack_from(">hIh", body, 0)
                rate = _ieee_extended(body[8:18])
                width = (bits + 7) // 8
                if compressed and len(body) >= 22:
                    codec = body[18:22]
                    if codec in (b"fl32", b"FL32"):
                        kind, width = "float", 4
                    elif codec in (b"fl64", b"FL64"):
                        kind, width = "float", 8
                    elif codec == b"sowt":
                        big_endian = False
                    elif codec not in (b"NONE", b"twos"):
                        raise DecodeError(f"compressed AIFF-C ({codec.decode('latin-1')}) is not supported")
            elif cid == b"SSND":
                offset = struct.unpack(">I", fh.read(4))[0]
                fh.read(4 + offset)
                if not rate or not channels or not width:
                    raise DecodeError("SSND before COMM chunk")
                frame_bytes = channels * width
                want = min(size - 8 - offset, int(max_seconds * rate) * frame_bytes)
                raw = fh.read(max(0, want - want % frame_bytes))
                break
            else:
                fh.seek(size + (size & 1), os.SEEK_CUR)
    data = _pcm_to_float(raw, width, kind, big_endian=big_endian)
    return data.reshape(-1, channels).mean(axis=1), int(round(rate))


def _read_soundfile(path: Path, max_seconds: float):
    try:
        import soundfile  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DecodeError(f"{path.suffix} needs the optional 'soundfile' package") from exc
    info = soundfile.info(str(path))
    data, rate = soundfile.read(str(path), frames=int(max_seconds * info.samplerate), dtype="float32",
                                always_2d=True)
    return data.mean(axis=1), rate


def load_mono(path: Path, *, max_seconds: float = ANALYSIS_SECONDS):
    """Mono float32 samples (first ``max_seconds``) and sample rate."""
    suffix = path.suffix.lower()
    if suffix in (".wav", ".wave"):
        return _read_wav(path, max_seconds)
    if suffix in (".aif", ".aiff", ".aifc"):
        return _read_aiff(path, max_seconds)
    if suffix in OPTIONAL_EXTS:
        return _read_soundfile(path, max_seconds)
    raise DecodeError(f"unsupported file type {suffix}")


def _resample(signal, rate: int):
    """Cheap linear resample to TARGET_RATE; band edges are fixed in Hz so this only bounds cost."""
    import numpy as np

    if rate == TARGET_RATE or signal.size == 0:
        return signal
    n = int(round(signal.size * TARGET_RATE / rate))
    if n < 2:
        return signal[:0]
    return np.interp(np.linspace(0, signal.size - 1, n), np.arange(signal.size), signal).astype(np.float32)


# --------------------------------------------------------------------------- features


def _band_matrix(n_bins: int, rate: int):
    import numpy as np

    freqs = np.linspace(0, rate / 2, n_bins)
    top = min(16000.0, rate / 2 * 0.98)
    edges = np.geomspace(40.0, top, N_BANDS + 1)
    matrix = np.zeros((N_BANDS, n_bins), dtype=np.float32)
    for i in range(N_BANDS):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if not mask.any():  # very narrow low bands: take the nearest bin
            mask[int(np.argmin(np.abs(freqs - (edges[i] + edges[i + 1]) / 2)))] = True
        matrix[i, mask] = 1.0 / mask.sum()
    return matrix, freqs


def compute_features(signal, rate: int) -> list[float]:
    """Fixed-length timbre vector for a mono signal (see FEATURE_NAMES)."""
    import numpy as np

    duration = signal.size / rate if rate else 0.0
    x = _resample(np.asarray(signal, dtype=np.float32), rate)
    if x.size < int(MIN_SECONDS * TARGET_RATE):
        raise DecodeError("too short to analyse")
    peak = float(np.max(np.abs(x))) or 0.0
    if peak < 1e-6:
        raise DecodeError("silent")
    x = x / peak
    if x.size < FRAME:
        x = np.pad(x, (0, FRAME - x.size))
    frames = np.lib.stride_tricks.sliding_window_view(x, FRAME)[::HOP]
    window = np.hanning(FRAME).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1)).astype(np.float32)
    power = spectrum ** 2
    matrix, freqs = _band_matrix(spectrum.shape[1], TARGET_RATE)
    bands_db = 10 * np.log10(power @ matrix.T + 1e-10)  # frames x bands
    frame_energy = power.sum(axis=1)
    loud = frame_energy >= frame_energy.max() * 1e-3  # ignore near-silent tails
    active = bands_db[loud] if loud.any() else bands_db
    envelope = active.mean(axis=0)
    envelope = envelope - envelope.max()  # level-invariant spectral shape
    motion = active.std(axis=0)

    total = power.sum(axis=1) + 1e-12
    centroid_hz = (power * freqs).sum(axis=1) / total
    centroid = np.log2(centroid_hz[loud] + 1.0) if loud.any() else np.log2(centroid_hz + 1.0)
    cumulative = np.cumsum(power, axis=1)
    rolloff_idx = (cumulative >= 0.85 * cumulative[:, -1:]).argmax(axis=1)
    rolloff = np.log2(freqs[rolloff_idx][loud] + 1.0).mean() if loud.any() else 0.0
    geo = np.exp(np.log(power + 1e-12).mean(axis=1))
    flatness = float((geo / (power.mean(axis=1) + 1e-12))[loud].mean()) if loud.any() else 0.0
    zcr = float(np.mean(np.abs(np.diff(np.signbit(x).astype(np.int8)))))

    flux = np.maximum(0.0, np.diff(np.log1p(spectrum), axis=0)).sum(axis=1)
    onset_rate = 0.0
    if flux.size > 2:
        threshold = flux.mean() + 1.5 * flux.std()
        peaks = (flux[1:-1] > threshold) & (flux[1:-1] >= flux[:-2]) & (flux[1:-1] >= flux[2:])
        onset_rate = float(peaks.sum()) / max(duration, 0.05)
    rms = np.sqrt(frame_energy / FRAME)
    peak_frame = int(np.argmax(rms))
    attack_pos = peak_frame / max(1, rms.size - 1)
    half = rms.size // 2
    decay = float(np.log10((rms[half:].mean() + 1e-9) / (rms[:half].mean() + 1e-9))) if rms.size >= 4 else 0.0
    crest = float(np.log10(1.0 / (np.sqrt(np.mean(x ** 2)) + 1e-9)))

    vector = np.concatenate([
        envelope / 10.0,
        motion / 10.0,
        [float(centroid.mean()), float(centroid.std()), float(rolloff), flatness * 10.0, zcr * 10.0,
         float(np.log1p(onset_rate)), attack_pos, decay, float(np.log2(max(duration, 0.01))), crest],
    ])
    return [round(float(v), 5) for v in vector]


# --------------------------------------------------------------------------- embedding extensions


def _embedders() -> list[tuple[str, Callable[[str], Any]]]:
    try:
        from audiotheca import extensions
    except ImportError:
        return []
    out = []
    for module in extensions.load()[0]:
        hook = getattr(module, "embed_audio", None)
        if callable(hook):
            out.append((Path(getattr(module, "__file__", "")).stem, hook))
    return out[:1]  # one embedding space per index


# --------------------------------------------------------------------------- index


def _load() -> dict[str, Any]:
    if not INDEX_PATH.is_file():
        return {"version": FEATURE_VERSION, "roots": [], "entries": {}, "skipped": {}, "indexed_at": None,
                "embedder": None}
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    if data.get("version") != FEATURE_VERSION:
        data = {"version": FEATURE_VERSION, "roots": data.get("roots", [])}
    for key, default in (("roots", []), ("entries", {}), ("skipped", {}), ("indexed_at", None),
                         ("embedder", None)):
        data.setdefault(key, default)
    return data


def _iter_audio(root: Path, *, max_depth: int = 12):
    stack = [(root, 0)]
    exts = NATIVE_EXTS | OPTIONAL_EXTS
    while stack:
        current, depth = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in sorted(entries, key=lambda e: e.name):
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if depth < max_depth and entry.name.lower() not in _SKIP_DIRS:
                                stack.append((Path(entry.path), depth + 1))
                        elif (entry.is_file(follow_symlinks=False) and not entry.name.startswith("._")
                              and Path(entry.name).suffix.lower() in exts):
                            yield Path(entry.path), entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
        except OSError:
            continue


def analyse_file(path: Path, *, embedder: tuple[str, Callable[[str], Any]] | None = None) -> dict[str, Any]:
    signal, rate = load_mono(path)
    row: dict[str, Any] = {"features": compute_features(signal, rate),
                           "duration_s": round(signal.size / rate, 3) if rate else 0.0}
    if embedder is not None:
        vector = embedder[1](str(path))
        row["embedding"] = [round(float(v), 6) for v in list(vector)[:4096]]
    return row


def index_samples(roots: list[str] | None = None, *, max_files: int = 2000,
                  progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    """Analyse new or changed files under ``roots`` (up to ``max_files`` per call; call again to continue)."""
    data = _load()
    roots = [str(r) for r in (roots if roots is not None else data["roots"])]
    embedders = _embedders()
    embedder = embedders[0] if embedders else None
    embedder_name = embedder[0] if embedder else None
    if data.get("embedder") != embedder_name:
        for entry in data["entries"].values():
            entry.pop("embedding", None)
            entry["stale"] = True
    entries: dict[str, Any] = data["entries"]
    skipped: dict[str, Any] = data["skipped"]
    seen: set[str] = set()
    pending: list[tuple[Path, os.stat_result]] = []
    for root in roots:
        for path, stat in _iter_audio(Path(root)):
            key = str(path)
            seen.add(key)
            old = entries.get(key) or skipped.get(key)
            if old and old.get("size") == stat.st_size and old.get("mtime") == stat.st_mtime and not old.get("stale"):
                continue
            pending.append((path, stat))
    analysed = 0
    for path, stat in pending[:max_files]:
        key = str(path)
        try:
            row = analyse_file(path, embedder=embedder)
            row.update({"size": stat.st_size, "mtime": stat.st_mtime})
            entries[key] = row
            skipped.pop(key, None)
        except (DecodeError, OSError, struct.error, ValueError) as exc:
            entries.pop(key, None)
            skipped[key] = {"size": stat.st_size, "mtime": stat.st_mtime, "reason": str(exc)[:160]}
        except Exception as exc:  # noqa: BLE001 - an extension embedder failed
            entries.pop(key, None)
            skipped[key] = {"size": stat.st_size, "mtime": stat.st_mtime, "reason": f"embedder: {exc}"[:160]}
        analysed += 1
        if progress:
            progress(analysed, min(len(pending), max_files))
    under_roots = tuple(os.path.join(r, "") for r in roots)
    for store in (entries, skipped):
        for key in [k for k in store if k not in seen and (not k.startswith(under_roots) or not Path(k).exists())]:
            store.pop(key)
    with locked(INDEX_PATH.with_suffix(".lock")):
        data.update({"roots": roots, "entries": entries, "skipped": skipped, "indexed_at": _now_iso(),
                     "embedder": embedder_name})
        write_json(INDEX_PATH, data)
    _CACHE["key"] = None
    result = status()
    result.update({"analysed": analysed, "remaining": max(0, len(pending) - max_files)})
    return result


def status() -> dict[str, Any]:
    data = _load()
    reasons: dict[str, int] = {}
    for row in data["skipped"].values():
        reason = str(row.get("reason", "")).split(":")[0][:60]
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "roots": data["roots"],
        "indexed_at": data["indexed_at"],
        "count": len(data["entries"]),
        "skipped": len(data["skipped"]),
        "skip_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])[:8]),
        "embedder": data["embedder"],
        "method": f"embedding ({data['embedder']})" if data["embedder"] else "spectral features",
    }


def set_roots(roots: list[str]) -> list[str]:
    clean = [str(r).strip() for r in roots if str(r).strip()]
    with locked(INDEX_PATH.with_suffix(".lock")):
        data = _load()
        data["roots"] = clean
        write_json(INDEX_PATH, data)
    return clean


# --------------------------------------------------------------------------- search

_CACHE: dict[str, Any] = {"key": None}


def _matrix(data: dict[str, Any]):
    """Normalized search matrix, cached by index mtime."""
    import numpy as np

    try:
        key = (INDEX_PATH.stat().st_mtime_ns, len(data["entries"]))
    except OSError:
        key = None
    if key is not None and _CACHE.get("key") == key:
        return _CACHE
    paths = list(data["entries"].keys())
    use_embedding = bool(data.get("embedder")) and paths and all("embedding" in data["entries"][p] for p in paths)
    if not paths:
        _CACHE.update({"key": key, "paths": [], "matrix": np.zeros((0, 1)), "mean": None, "std": None,
                       "embedding": False})
        return _CACHE
    if use_embedding:
        raw = np.array([data["entries"][p]["embedding"] for p in paths], dtype=np.float32)
        mean = np.zeros(raw.shape[1], dtype=np.float32)
        std = np.ones(raw.shape[1], dtype=np.float32)
        weights = np.ones(raw.shape[1], dtype=np.float32)
    else:
        raw = np.array([data["entries"][p]["features"] for p in paths], dtype=np.float32)
        mean = raw.mean(axis=0)
        std = raw.std(axis=0) + 1e-6
        weights = np.array(_WEIGHTS, dtype=np.float32)
    norm = (raw - mean) / std * weights
    norm /= np.linalg.norm(norm, axis=1, keepdims=True) + 1e-9
    _CACHE.update({"key": key, "paths": paths, "matrix": norm, "mean": mean, "std": std, "weights": weights,
                   "embedding": use_embedding, "index": {p: i for i, p in enumerate(paths)}})
    return _CACHE


MIN_SCORE = 0.15  # below this a "match" is noise; showing it only confuses


def similar_to(path: str, *, limit: int = 25, exclude_same_folder: bool = False,
               max_duration_ratio: float | None = None, min_score: float = MIN_SCORE) -> dict[str, Any]:
    """Nearest samples to ``path`` (indexed or not) by cosine similarity, best first."""
    import numpy as np

    data = _load()
    cache = _matrix(data)
    if not cache["paths"]:
        return {"query": path, "results": [], "method": status()["method"]}
    target = Path(path)
    entry = data["entries"].get(str(target))
    if entry is None:
        embedders = _embedders() if cache["embedding"] else []
        entry = analyse_file(target, embedder=embedders[0] if embedders else None)
    vector = np.array(entry["embedding"] if cache["embedding"] else entry["features"], dtype=np.float32)
    query = (vector - cache["mean"]) / cache["std"] * cache["weights"]
    query /= np.linalg.norm(query) + 1e-9
    scores = cache["matrix"] @ query
    order = np.argsort(-scores)
    results = []
    folder = str(target.parent)
    duration = float(entry.get("duration_s") or 0)
    for i in order:
        candidate = cache["paths"][int(i)]
        if float(scores[int(i)]) < min_score:
            break  # scores are sorted, so nothing after this qualifies
        if candidate == str(target):
            continue
        if exclude_same_folder and str(Path(candidate).parent) == folder:
            continue
        other = data["entries"][candidate]
        if max_duration_ratio and duration > 0:
            ratio = max(duration, other.get("duration_s", 0) or 1e-6) / max(min(duration, other.get("duration_s", 0)), 1e-6)
            if ratio > max_duration_ratio:
                continue
        results.append({"path": candidate, "name": Path(candidate).name, "folder": str(Path(candidate).parent),
                        "score": round(float(scores[int(i)]), 4), "duration_s": other.get("duration_s")})
        if len(results) >= limit:
            break
    return {"query": str(target), "duration_s": entry.get("duration_s"), "results": results,
            "method": status()["method"]}


def search_names(text: str, *, limit: int = 50) -> list[dict[str, Any]]:
    """Indexed samples whose path contains every word of ``text`` (to pick a query sample)."""
    words = [w for w in text.lower().split() if w]
    if not words:
        return []
    out = []
    for path, row in _load()["entries"].items():
        low = path.lower()
        if all(w in low for w in words):
            out.append({"path": path, "name": Path(path).name, "duration_s": row.get("duration_s")})
            if len(out) >= limit:
                break
    return out
