"""UCS write-back — batch rename sound effects to the Universal Category System and tag them.

UCS filenames look like ``CatID_FXName_CreatorID_SourceID[_UserData].wav``,
for example ``DOORWood_Creaky Door Open Slow_JD_BackyardSFX.wav``.

* **Rename** moves go through the transaction ledger (op ``ucs_rename``), so a
  batch can be undone from the audit log like any other move.
* **Metadata** writes an iXML chunk (``<USER>`` CATID / CATEGORY / SUBCATEGORY /
  FXNAME / CREATORID / SOURCEID plus ``<UCS>``) into WAV/BWF files. The original
  file is copied to ``dedupe_reports/ucs_backups/<batch>/`` first and
  ``undo_metadata`` restores it. Audio sample data is verified unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from api.paths import report_dir

BACKUP_ROOT = report_dir() / "ucs_backups"
_CATID_RE = re.compile(r"^[A-Z]{2,8}[A-Za-z]{1,12}$")
_FIELD_ILLEGAL = re.compile(r'[_<>:"/\\|?*\x00-\x1f]')
_WAV_EXTS = {".wav", ".bwf"}
_MAX_RIFF = 0xFFFFFFFF


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: str, *, limit: int = 60) -> str:
    text = _FIELD_ILLEGAL.sub(" ", text or "")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def split_catid(cat_id: str) -> tuple[str, str]:
    """``DOORWood`` → (``DOOR``, ``Wood``): the upper-case prefix is the category."""
    match = re.match(r"^([A-Z]+)([A-Z][a-z].*|[a-z].*)?$", cat_id)
    if not match:
        return cat_id, ""
    return match.group(1), match.group(2) or ""


def fx_name_from(stem: str) -> str:
    stem = re.sub(r"(?i)[_\-.]+", " ", stem)
    return _clean(stem.title() if stem.islower() or stem.isupper() else stem)


def ucs_name(*, cat_id: str, fx_name: str, creator_id: str, source_id: str, user_data: str = "",
             ext: str = ".wav") -> str:
    if not _CATID_RE.match(cat_id or ""):
        raise ValueError("CatID must look like DOORWood: an upper-case category then a subcategory")
    parts = [cat_id, _clean(fx_name), _clean(creator_id, limit=20), _clean(source_id, limit=40)]
    if not all(parts):
        raise ValueError("CatID, FX name, creator ID and source ID are all required")
    if user_data:
        parts.append(_clean(user_data, limit=40))
    return "_".join(parts) + ext.lower()


def plan(paths: list[str], *, cat_id: str, creator_id: str, source_id: str, user_data: str = "",
         fx_names: dict[str, str] | None = None) -> dict[str, Any]:
    from ucs_map import parse_ucs_filename

    rows: list[dict[str, Any]] = []
    targets: dict[str, int] = {}
    for raw in paths:
        path = Path(raw)
        fx = (fx_names or {}).get(raw) or fx_name_from(path.stem)
        try:
            new_name = ucs_name(cat_id=cat_id, fx_name=fx, creator_id=creator_id, source_id=source_id,
                                user_data=user_data, ext=path.suffix or ".wav")
            error = ""
        except ValueError as exc:
            new_name, error = "", str(exc)
        target = str(path.with_name(new_name)) if new_name else ""
        targets[target.lower()] = targets.get(target.lower(), 0) + 1
        rows.append({"path": raw, "name": path.name, "fx_name": fx, "new_name": new_name, "target": target,
                     "already_ucs": parse_ucs_filename(path.name).get("ucs_aligned", False), "error": error,
                     "unchanged": new_name == path.name})
    for row in rows:
        if row["target"] and targets[row["target"].lower()] > 1:
            # Number clashing FX names so every file stays unique.
            row["error"] = row["error"] or "Two files would get the same name; give them distinct FX names"
        elif row["target"] and os.path.lexists(row["target"]) and not row["unchanged"]:
            row["error"] = row["error"] or "A file with the new name already exists"
    return {"cat_id": cat_id, "rows": rows, "ok": sum(1 for r in rows if not r["error"] and not r["unchanged"]),
            "errors": sum(1 for r in rows if r["error"])}


def apply_renames(planned: dict[str, Any], *, batch_id: str | None = None) -> dict[str, Any]:
    from audiotheca import transaction_ledger as ledger

    batch = batch_id or ledger.new_batch_id()
    results = []
    for row in planned["rows"]:
        if row["error"] or row["unchanged"] or not row["target"]:
            continue
        ok, error = ledger.guarded_move(Path(row["path"]), Path(row["target"]), batch_id=batch, op="ucs_rename",
                                        meta={"cat_id": planned["cat_id"]})
        results.append({"path": row["path"], "target": row["target"], "ok": ok, "error": error})
    return {"batch_id": batch, "renamed": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]), "results": results}


# ── iXML metadata ────────────────────────────────────────────────────────────


def _chunks(path: Path) -> tuple[bytes, list[tuple[bytes, int, int]]]:
    """RIFF form type and (id, payload offset, payload size) for every chunk."""
    with path.open("rb") as handle:
        header = handle.read(12)
        if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise ValueError("Not a RIFF/WAVE file (RF64 and W64 are not supported)")
        form = header[8:12]
        chunks = []
        size = path.stat().st_size
        offset = 12
        while offset + 8 <= size:
            handle.seek(offset)
            chunk_id, length = struct.unpack("<4sI", handle.read(8))
            chunks.append((chunk_id, offset + 8, length))
            offset += 8 + length + (length % 2)
    return form, chunks


def _audio_digest(path: Path) -> str:
    _form, chunks = _chunks(path)
    data = [c for c in chunks if c[0] == b"data"]
    if not data:
        raise ValueError("WAV file has no data chunk")
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        handle.seek(data[0][1])
        remaining = data[0][2]
        while remaining > 0:
            block = handle.read(min(remaining, 1024 * 1024))
            if not block:
                break
            hasher.update(block)
            remaining -= len(block)
    return hasher.hexdigest()


def ixml_payload(*, cat_id: str, fx_name: str, creator_id: str, source_id: str, user_data: str = "") -> bytes:
    from ucs_map import category_label

    category, sub = split_catid(cat_id)
    fields = {
        "CATID": cat_id, "CATEGORY": category_label(category), "SUBCATEGORY": sub, "FXNAME": fx_name,
        "CREATORID": creator_id, "SOURCEID": source_id, "USERDATA": user_data,
    }
    user = "".join(f"<{k}>{escape(v)}</{k}>" for k, v in fields.items() if v)
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><BWFXML><IXML_VERSION>2.10</IXML_VERSION>'
           f"<USER>{user}</USER><UCS>{user}</UCS></BWFXML>")
    return xml.encode("utf-8")


def write_ixml(path: Path, payload: bytes) -> None:
    """Rewrite ``path`` with its iXML chunk replaced. Audio data is verified unchanged."""
    form, chunks = _chunks(path)
    before = _audio_digest(path)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".ucs", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as out, path.open("rb") as src:
            out.write(b"RIFF\0\0\0\0" + form)
            for chunk_id, offset, length in chunks:
                if chunk_id == b"iXML":
                    continue
                src.seek(offset - 8)
                remaining = 8 + length + (length % 2)
                while remaining > 0:
                    block = src.read(min(remaining, 1024 * 1024))
                    if not block:
                        break
                    out.write(block)
                    remaining -= len(block)
            out.write(b"iXML" + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) % 2 else b""))
            total = out.tell()
            if total - 8 > _MAX_RIFF:
                raise ValueError("File would exceed the 4 GB RIFF limit")
            out.seek(4)
            out.write(struct.pack("<I", total - 8))
            out.flush()
            os.fsync(out.fileno())
        if _audio_digest(temp) != before:
            raise OSError("Audio data changed while writing metadata")
        shutil.copystat(path, temp)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def apply_metadata(paths: list[str], *, cat_id: str, creator_id: str, source_id: str, user_data: str = "",
                   fx_names: dict[str, str] | None = None) -> dict[str, Any]:
    batch = datetime.now().strftime("%Y%m%d_%H%M%S_") + hashlib.sha1(os.urandom(8)).hexdigest()[:6]
    backup_dir = BACKUP_ROOT / batch
    manifest: list[dict[str, str]] = []
    results = []
    for raw in paths:
        path = Path(raw)
        if path.suffix.lower() not in _WAV_EXTS:
            results.append({"path": raw, "ok": False, "error": "Only WAV/BWF files take iXML metadata"})
            continue
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup = backup_dir / f"{len(manifest):05d}_{path.name}"
            shutil.copy2(path, backup)
            manifest.append({"path": str(path), "backup": str(backup)})
            _write_manifest(backup_dir, manifest)
            fx = (fx_names or {}).get(raw) or fx_name_from(path.stem)
            write_ixml(path, ixml_payload(cat_id=cat_id, fx_name=fx, creator_id=creator_id, source_id=source_id,
                                          user_data=user_data))
            results.append({"path": raw, "ok": True})
        except (OSError, ValueError) as exc:
            results.append({"path": raw, "ok": False, "error": str(exc)})
    return {"batch": batch if manifest else None, "written": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]), "results": results}


def _write_manifest(folder: Path, rows: list[dict[str, str]]) -> None:
    (folder / "manifest.json").write_text(json.dumps({"created": _now_iso(), "files": rows}, indent=2),
                                          encoding="utf-8")


def list_metadata_batches() -> list[dict[str, Any]]:
    out = []
    if not BACKUP_ROOT.is_dir():
        return out
    for folder in BACKUP_ROOT.iterdir():
        manifest = folder / "manifest.json"
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out.append({"batch": folder.name, "created": data.get("created"), "files": len(data.get("files", [])),
                        "restored": bool(data.get("restored"))})
    out.sort(key=lambda row: row.get("created") or "", reverse=True)
    return out[:50]


def undo_metadata(batch: str) -> dict[str, Any]:
    if not re.fullmatch(r"\d{8}_\d{6}_[0-9a-f]{6}", batch or ""):
        raise ValueError("Unknown metadata batch")
    folder = BACKUP_ROOT / batch
    manifest_path = folder / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    restored, errors = 0, []
    for row in data.get("files", []):
        try:
            target = Path(row["path"])
            temp = target.with_name(f".{target.name}.restore")
            shutil.copy2(row["backup"], temp)
            os.replace(temp, target)
            restored += 1
        except OSError as exc:
            errors.append({"path": row.get("path"), "error": str(exc)})
    data["restored"] = _now_iso()
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"batch": batch, "restored": restored, "errors": errors}
