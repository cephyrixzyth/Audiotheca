"""Parse BWF axml / iXML chunks from WAV files for vendor hints."""

from __future__ import annotations

import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

VENDOR_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Boom Library", re.compile(r"boom\s*library", re.I)),
    ("Sound Ideas", re.compile(r"sound\s*ideas", re.I)),
    ("Pro Sound Effects", re.compile(r"pro\s*sound\s*effects", re.I)),
    ("Epic Stock Media", re.compile(r"epic\s*stock", re.I)),
    ("Soniss", re.compile(r"\bsoniss\b", re.I)),
    ("Sample Logic", re.compile(r"sample\s*logic", re.I)),
    ("Impact Soundworks", re.compile(r"impact\s*soundworks", re.I)),
    ("Audio Imperia", re.compile(r"audio\s*imperia", re.I)),
    ("Heavyocity", re.compile(r"heavyocity", re.I)),
    ("Spitfire Audio", re.compile(r"spitfire\s*audio", re.I)),
]

BEXT_FIELD_SIZE = 256
BEXT_UMID_SIZE = 64


def _read_chunk(f, max_payload: int = 8 * 1024 * 1024) -> tuple[bytes, int] | None:
    header = f.read(8)
    if len(header) < 8:
        return None
    chunk_id, size = struct.unpack("<4sI", header)
    if size > max_payload:
        f.seek(size, 1)
        return chunk_id, size
    payload = f.read(size)
    if size % 2:
        f.read(1)
    return chunk_id, payload


def _decode_field(raw: bytes) -> str:
    text = raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
    return text


def _parse_bext_binary(payload: bytes) -> dict[str, str]:
    """Parse fixed-width BWF bext chunk fields (EBU Tech 3285)."""
    if len(payload) < BEXT_FIELD_SIZE * 2 + BEXT_UMID_SIZE + 4:
        return {}
    offset = 0
    description = _decode_field(payload[offset : offset + BEXT_FIELD_SIZE])
    offset += BEXT_FIELD_SIZE
    originator = _decode_field(payload[offset : offset + BEXT_FIELD_SIZE])
    offset += BEXT_FIELD_SIZE
    originator_ref = _decode_field(payload[offset : offset + BEXT_FIELD_SIZE])
    offset += BEXT_FIELD_SIZE
    return {
        "bext_description": description,
        "bext_originator": originator,
        "bext_originator_reference": originator_ref,
    }


def _scan_wav_chunks(path: Path) -> dict[str, str]:
    chunks: dict[str, str] = {}
    bext_fields: dict[str, str] = {}
    with path.open("rb") as handle:
        if handle.read(4) != b"RIFF":
            return chunks
        handle.read(4)
        if handle.read(4) != b"WAVE":
            return chunks
        while True:
            item = _read_chunk(handle)
            if item is None:
                break
            chunk_id, payload = item
            if isinstance(payload, int):
                continue
            label = chunk_id.decode("ascii", "replace").strip("\x00")
            if label == "bext":
                bext_fields = _parse_bext_binary(payload)
                try:
                    chunks[label] = payload.decode("utf-8", errors="replace")
                except UnicodeDecodeError:
                    chunks[label] = payload.decode("latin-1", errors="replace")
            elif label in ("axml", "iXML", "LIST"):
                try:
                    chunks[label] = payload.decode("utf-8", errors="replace")
                except UnicodeDecodeError:
                    chunks[label] = payload.decode("latin-1", errors="replace")
    if bext_fields:
        chunks.update({f"_{k}": v for k, v in bext_fields.items() if v})
    return chunks


def _vendor_hints_from_text(text: str) -> list[str]:
    hints: list[str] = []
    for name, pattern in VENDOR_PATTERNS:
        if pattern.search(text):
            hints.append(name)
    return hints


def _vendor_hints_from_xml(text: str) -> list[str]:
    hints: list[str] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return _vendor_hints_from_text(text)
    blob = ET.tostring(root, encoding="unicode", method="text")
    hints.extend(_vendor_hints_from_text(blob))
    for tag in ("USER", "PROJECT", "NOTE", "ORIGINATOR", "ORIGINATOR_REFERENCE"):
        node = root.find(f".//{tag}")
        if node is not None and node.text:
            hints.extend(_vendor_hints_from_text(node.text))
    return list(dict.fromkeys(hints))


def parse_wav_metadata(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.suffix.lower() not in {".wav", ".wave"}:
        return {"path": str(path), "vendor_hints": [], "chunks": [], "error": "not_a_wav"}

    try:
        chunks = _scan_wav_chunks(path)
    except OSError as exc:
        return {"path": str(path), "vendor_hints": [], "chunks": [], "error": str(exc)}

    vendor_hints: list[str] = []
    bext_meta: dict[str, str] = {}
    for label, text in chunks.items():
        if label.startswith("_bext_"):
            bext_meta[label[1:]] = text
            vendor_hints.extend(_vendor_hints_from_text(text))
        elif label in ("axml", "iXML"):
            vendor_hints.extend(_vendor_hints_from_xml(text))
        elif label == "bext":
            vendor_hints.extend(_vendor_hints_from_text(text))
        elif label not in ("LIST",):
            vendor_hints.extend(_vendor_hints_from_text(text))

    return {
        "path": str(path),
        "vendor_hints": list(dict.fromkeys(vendor_hints)),
        "bext": bext_meta,
        "chunks": sorted(k for k in chunks.keys() if not k.startswith("_")),
        "error": None,
    }
