"""Remaining 2026-11-28 review features: more DAW formats, sample similarity finder, shared catalog."""

from __future__ import annotations

import json
import struct
import wave
import zipfile
from pathlib import Path

import numpy as np
import pytest

from audiotheca import daw_projects, plugin_ledger, release_monitor, sample_similarity, shared_catalog, vendor_overrides


@pytest.fixture
def stores(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    monkeypatch.setattr(daw_projects, "INDEX_PATH", reports / "daw_project_index.json")
    monkeypatch.setattr(plugin_ledger, "STORE_PATH", reports / "plugin_ledger.json")
    monkeypatch.setattr(sample_similarity, "INDEX_PATH", reports / "sample_similarity_index.json")
    sample_similarity._CACHE["key"] = None
    monkeypatch.setattr(sample_similarity, "_embedders", lambda: [])
    monkeypatch.setattr(shared_catalog, "STORE_PATH", reports / "shared_catalog.json")
    monkeypatch.setattr(shared_catalog, "KEY_PATH", reports / ".catalog_signing.key")
    monkeypatch.setattr(shared_catalog, "report_dir", lambda: reports)
    monkeypatch.setattr(release_monitor, "STORE_PATH", reports / "release_monitor.json")
    monkeypatch.setattr(vendor_overrides, "FEEDBACK_DIR", reports / "feedback")
    monkeypatch.setattr(vendor_overrides, "OVERRIDES_PATH", reports / "feedback" / "vendor_overrides.json")
    monkeypatch.setattr(vendor_overrides, "_vendors_from_investigation_store", lambda: [])
    monkeypatch.delenv("AUDIOTHECA_AIR_GAP", raising=False)
    return reports


# ── DAW formats ─────────────────────────────────────────────────────────────


def _flp_text(event: int, text: str, utf16: bool = True) -> bytes:
    data = (text + "\x00").encode("utf-16le" if utf16 else "utf-8")
    size = len(data)
    varint = bytearray()
    while True:
        byte = size & 0x7F
        size >>= 7
        varint.append(byte | (0x80 if size else 0))
        if not size:
            break
    return bytes([event]) + bytes(varint) + data


def _flp(events: bytes) -> bytes:
    header = b"FLhd" + struct.pack("<I", 6) + struct.pack("<hhh", 0, 3, 96)
    return header + b"FLdt" + struct.pack("<I", len(events)) + events


def test_fl_studio_wrapped_and_native_plugins(tmp_path):
    events = (bytes([0x40, 0x01, 0x00])  # a 2-byte event to skip
              + _flp_text(201, "Fruity Wrapper") + _flp_text(203, "Serum")
              + _flp_text(201, "Sytrus") + _flp_text(203, "My Sytrus")
              + _flp_text(196, r"C:\Samples\Kicks\Kick 01.wav")
              + bytes([0x80]) + struct.pack("<I", 7))  # a 4-byte event
    path = tmp_path / "beat.flp"
    path.write_bytes(_flp(events))
    parsed = daw_projects.parse_fl_studio(path)
    assert {"format": "VST", "name": "Serum", "vendor": ""} in parsed["plugins"]
    assert {"format": "FL Studio", "name": "Sytrus", "vendor": "Image-Line"} in parsed["plugins"]
    assert not any(p["name"] == "My Sytrus" for p in parsed["plugins"])
    assert parsed["samples"] == [r"C:\Samples\Kicks\Kick 01.wav"]


def test_fl_studio_rejects_other_files(tmp_path):
    path = tmp_path / "x.flp"
    path.write_bytes(b"RIFF0000")
    with pytest.raises(ValueError):
        daw_projects.parse_fl_studio(path)


def test_studio_one_song(tmp_path):
    path = tmp_path / "Track.song"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("Devices/audiomixer.xml",
                    '<AudioMixer><Attributes x:id="classInfo" classID="{1234}" name="Pro-Q 3" '
                    'category="AudioEffect" subCategory="(Native) VST3"/>'
                    '<Attributes classID="{99}" name="Fat Channel" category="AudioEffect"/>'
                    '<Attributes classID="{88}" name="Track 1" category="Track"/></AudioMixer>')
        zf.writestr("Song/mediapool.xml",
                    '<MediaPool><AudioClip><Url x:id="path" url="file:///C:/Samples/Snare%2001.wav"/></AudioClip>'
                    '<AudioClip><Url url="file:///Users/me/Loops/loop.aif"/></AudioClip></MediaPool>')
    parsed = daw_projects.parse_studio_one(path)
    names = {(p["format"], p["name"]) for p in parsed["plugins"]}
    assert ("VST3", "Pro-Q 3") in names and ("Studio One", "Fat Channel") in names
    assert "Track 1" not in {p["name"] for p in parsed["plugins"]}
    assert parsed["samples"] == ["/Users/me/Loops/loop.aif", "C:/Samples/Snare 01.wav"]


def test_heuristic_formats_and_logic_package(stores, tmp_path):
    plugin_ledger._save({"inventory": [{"format": "VST3", "product": "Diva", "vendor": "u-he"}]})
    root = tmp_path / "projects"
    root.mkdir()
    bitwig = (b"\x00\x01" + "C:\\Program Files\\Common Files\\VST3\\FabFilter Pro-Q 3.vst3".encode("utf-16le")
              + b"\x00\x00junk\x00Diva\x00" + b"/Users/me/Samples/hat.wav\x00" + b"Drums/rel.wav\x00")
    (root / "song.bwproject").write_bytes(bitwig)
    (root / "mix.cpr").write_bytes(b"\x00Plugin Name\x00\x00\x00\x06Serum\x00kernel32.dll\x00")
    logic = root / "Album.logicx"
    (logic / "Alternatives" / "000").mkdir(parents=True)
    (logic / "Alternatives" / "000" / "ProjectData").write_bytes(b"\x00\x00Diva\x00ValhallaRoom.component\x00")
    (logic / "Media" / "Audio Files").mkdir(parents=True)
    (logic / "Media" / "Audio Files" / "Vox.wav").write_bytes(b"RIFF")
    summary = daw_projects.index_projects([str(root)])
    assert summary["by_daw"] == {"bitwig": 1, "cubase": 1, "logic": 1}
    projects = {p["daw"]: p for p in daw_projects._load()["projects"]}
    bw = {p["name"] for p in projects["bitwig"]["plugins"]}
    assert bw == {"FabFilter Pro-Q 3", "Diva"}
    assert projects["bitwig"]["samples"] == ["/Users/me/Samples/hat.wav"]
    assert projects["bitwig"]["confidence"] == "heuristic"
    assert {p["name"] for p in projects["cubase"]["plugins"]} == {"Serum"}
    assert {p["name"] for p in projects["logic"]["plugins"]} == {"Diva", "ValhallaRoom"}
    assert projects["logic"]["samples"][0].endswith("Vox.wav")
    assert len(daw_projects.projects_using_plugin("Diva")) == 2


# ── Sample similarity ───────────────────────────────────────────────────────


def _wav(path: Path, x: np.ndarray, rate: int = 44100, width: int = 2, channels: int = 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.clip(x, -1, 1)
    if channels == 2:
        x = np.stack([x, x], axis=1).reshape(-1)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        if width == 2:
            handle.writeframes((x * 32767).astype("<i2").tobytes())
        else:
            ints = (x * 8388607).astype(np.int32)
            handle.writeframes(np.stack([ints & 255, (ints >> 8) & 255, (ints >> 16) & 255], 1)
                               .astype(np.uint8).tobytes())
    return path


def _float_wav(path: Path, x: np.ndarray, rate: int = 48000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = x.astype("<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def _aiff(path: Path, x: np.ndarray, rate: int = 44100) -> Path:
    data = (np.clip(x, -1, 1) * 32767).astype(">i2").tobytes()
    import math

    e = int(math.floor(math.log2(rate)))
    exponent, mantissa = 16383 + e, int(rate * 2 ** (63 - e))
    comm = struct.pack(">hIh", 1, len(x), 16) + struct.pack(">H", exponent) + mantissa.to_bytes(8, "big")
    ssnd = struct.pack(">II", 0, 0) + data
    body = b"AIFF" + b"COMM" + struct.pack(">I", len(comm)) + comm + b"SSND" + struct.pack(">I", len(ssnd)) + ssnd
    path.write_bytes(b"FORM" + struct.pack(">I", len(body)) + body)
    return path


def _library(root: Path) -> None:
    rng = np.random.default_rng(1)
    for i in range(3):
        t = np.arange(int(44100 * 0.5)) / 44100
        kick = np.sin(2 * np.pi * (50 + 8 * i) * t * (1 + 3 * np.exp(-t * 40))) * np.exp(-t * (8 + i))
        _wav(root / "kicks" / f"kick{i}.wav", kick, width=3 if i == 1 else 2, channels=2 if i == 2 else 1)
    for i in range(3):
        n = int(44100 * 0.15)
        hat = np.diff(rng.normal(0, 1, n), prepend=0) * np.exp(-np.arange(n) / 44100 * (30 + 5 * i))
        _wav(root / "hats" / f"hat{i}.wav", hat * 0.3)
    for i in range(3):
        t = np.arange(48000 * 3) / 48000
        pad = sum(np.sin(2 * np.pi * 220 * (1 + i * 0.12) * r * t) for r in (1, 1.25, 1.5)) / 3
        _float_wav(root / "pads" / f"pad{i}.wav", (pad * np.minimum(1, t * 2) * 0.5).astype(np.float32))


def test_decoders_agree(tmp_path):
    t = np.arange(4410) / 44100
    x = 0.5 * np.sin(2 * np.pi * 440 * t)
    a, ra = sample_similarity.load_mono(_wav(tmp_path / "a.wav", x))
    b, rb = sample_similarity.load_mono(_wav(tmp_path / "b.wav", x, width=3))
    c, rc = sample_similarity.load_mono(_aiff(tmp_path / "c.aif", x))
    d, rd = sample_similarity.load_mono(_float_wav(tmp_path / "d.wav", x.astype(np.float32), rate=44100))
    assert ra == rb == rc == rd == 44100
    for other in (b, c, d):
        assert np.allclose(a, other, atol=1e-3)


def test_similarity_groups_by_sound(stores, tmp_path):
    lib = tmp_path / "lib"
    _library(lib)
    (lib / "broken.wav").write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    (lib / "song.flac").write_bytes(b"fLaC")
    result = sample_similarity.index_samples([str(lib)])
    assert result["count"] == 9 and result["skipped"] == 2 and result["remaining"] == 0
    for query, family in (("kicks/kick0.wav", "kick"), ("hats/hat0.wav", "hat"), ("pads/pad0.wav", "pad")):
        found = sample_similarity.similar_to(str(lib / query), limit=2)["results"]
        assert [r["name"].startswith(family) for r in found] == [True, True], (query, found)
    # Second run is incremental, and a file outside the index can still be queried.
    assert sample_similarity.index_samples([str(lib)])["analysed"] == 0
    t = np.arange(int(44100 * 0.4)) / 44100
    probe = _wav(tmp_path / "probe.wav", np.sin(2 * np.pi * 55 * t * (1 + 3 * np.exp(-t * 40))) * np.exp(-t * 9))
    assert sample_similarity.similar_to(str(probe), limit=1)["results"][0]["name"].startswith("kick")
    other = sample_similarity.similar_to(str(lib / "kicks/kick0.wav"), exclude_same_folder=True, limit=3,
                                         min_score=-1.0)["results"]
    assert other and all(r["folder"] != str(lib / "kicks") for r in other)
    # Hats and pads are nothing like a kick, so by default they are not offered as matches.
    assert sample_similarity.similar_to(str(lib / "kicks/kick0.wav"), exclude_same_folder=True)["results"] == []
    assert [r["name"] for r in sample_similarity.search_names("hats hat1")] == ["hat1.wav"]


def test_similarity_max_files_and_removed_files(stores, tmp_path):
    lib = tmp_path / "lib"
    _library(lib)
    first = sample_similarity.index_samples([str(lib)], max_files=4)
    assert first["analysed"] == 4 and first["remaining"] == 5
    assert sample_similarity.index_samples([str(lib)])["count"] == 9
    (lib / "hats" / "hat2.wav").unlink()
    assert sample_similarity.index_samples([str(lib)])["count"] == 8


def test_similarity_uses_extension_embedding(stores, tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    _library(lib)
    monkeypatch.setattr(sample_similarity, "_embedders",
                        lambda: [("fake", lambda p: [1.0, 0.0] if "kick" in p else [0.0, 1.0])])
    sample_similarity.index_samples([str(lib)])
    assert sample_similarity.status()["method"] == "embedding (fake)"
    found = sample_similarity.similar_to(str(lib / "kicks/kick0.wav"), limit=2)["results"]
    assert all(r["name"].startswith("kick") and r["score"] > 0.99 for r in found)


# ── Shared catalog ──────────────────────────────────────────────────────────


def _seed_local():
    vendor_overrides.add_user_vendor("Acme Audio", ["acme", "acmesynth"])
    release_monitor.add_feed("Acme Audio", "https://acme.example/releases.xml")


def test_catalog_export_is_signed_and_has_no_paths(stores):
    _seed_local()
    bundle = shared_catalog.export_bundle("Studio rules", publisher_name="Chris")
    assert shared_catalog.verify(bundle)["state"] == "valid"
    text = json.dumps(bundle)
    assert str(stores) not in text
    assert bundle["entries"]["vendor_rules"] == [{"company": "Acme Audio", "keywords": ["acme", "acmesynth"],
                                                  "category": "User_Added"}]
    tampered = json.loads(text)
    tampered["entries"]["vendor_rules"][0]["keywords"].append("evil")
    assert shared_catalog.verify(tampered)["state"] == "invalid"
    with pytest.raises(shared_catalog.CatalogError):
        shared_catalog.apply(tampered)
    assert (stores / ".catalog_signing.key").stat().st_mode & 0o077 == 0


def _bundle(rules, feeds=()):
    return {"kind": "audiotheca.catalog", "version": 1, "name": "Community", "entries": {
        "vendor_rules": list(rules), "release_feeds": list(feeds)}}


def test_catalog_preview_and_selective_apply(stores):
    _seed_local()
    bundle = _bundle(
        [{"company": "Acme Audio", "keywords": ["acme", "acme fx"]},
         {"company": "Bolt Instruments", "keywords": ["bolt", "x"]},
         {"company": "Nope", "keywords": ["<script>"]}],
        [{"vendor": "Bolt Instruments", "url": "https://bolt.example/feed"},
         {"vendor": "Bad", "url": "http://insecure.example/feed"}])
    report = shared_catalog.preview(bundle)
    assert report["signature"]["state"] == "unsigned"
    assert {r["company"]: r["change"] for r in report["vendor_rules"]} == {"Acme Audio": "adds_keywords",
                                                                          "Bolt Instruments": "new"}
    assert report["dropped"] == 2 and report["changes"] == 3
    record = shared_catalog.apply(bundle, companies=["Acme Audio"], feed_urls=[])
    assert record["vendor_rules"] == 1 and record["release_feeds"] == 0
    vendors = {v.company: v.keywords for v in vendor_overrides.load_user_vendors()}
    assert vendors == {"Acme Audio": ["acme", "acmesynth", "acme fx"]}
    shared_catalog.apply(bundle)
    assert "Bolt Instruments" in {v.company for v in vendor_overrides.load_user_vendors()}
    assert {f["url"] for f in release_monitor.list_feeds()} == {"https://acme.example/releases.xml",
                                                                "https://bolt.example/feed"}
    assert shared_catalog.preview(bundle)["changes"] == 0


def test_catalog_subscription_pins_key(stores, monkeypatch):
    _seed_local()
    signed = shared_catalog.export_bundle("Acme rules")
    sub = shared_catalog.add_subscription("https://catalog.example/acme.json")
    with pytest.raises(shared_catalog.CatalogError):
        shared_catalog.add_subscription("https://catalog.example/acme.json")
    payload = json.dumps(signed).encode()
    result = shared_catalog.refresh(sub["id"], fetch=lambda url: payload)
    assert result["subscription"]["pinned_fingerprint"] == shared_catalog.verify(signed)["fingerprint"]
    assert result["preview"]["changes"] == 0
    # A different publisher key for the same URL is refused.
    (stores / ".catalog_signing.key").unlink()
    other = shared_catalog.export_bundle("Acme rules")
    result = shared_catalog.refresh(sub["id"], fetch=lambda url: json.dumps(other).encode())
    assert result["preview"]["signature"]["state"] == "key_changed"
    assert "different key" in shared_catalog.list_subscriptions()[0]["last_error"]
    with pytest.raises(shared_catalog.CatalogError):
        shared_catalog.apply_subscription(sub["id"])
    assert shared_catalog.remove_subscription(sub["id"])


def test_catalog_trust_and_rejects(stores):
    signed = shared_catalog.export_bundle("Mine")
    fp = shared_catalog.verify(signed)["fingerprint"]
    shared_catalog.trust(fp, "Me")
    assert shared_catalog.preview(signed)["signature"]["state"] == "trusted"
    for raw in (b"not json", json.dumps({"kind": "other"}).encode(),
                json.dumps({"kind": "audiotheca.catalog", "version": 99}).encode()):
        with pytest.raises(shared_catalog.CatalogError):
            shared_catalog.parse_bundle(raw)
    with pytest.raises(shared_catalog.CatalogError):
        shared_catalog.add_subscription("http://catalog.example/x.json")


def test_catalog_air_gap_blocks_fetch(stores, monkeypatch):
    monkeypatch.setenv("AUDIOTHECA_AIR_GAP", "1")
    with pytest.raises(PermissionError):
        shared_catalog._fetch("https://catalog.example/x.json")


# ── API ─────────────────────────────────────────────────────────────────────


def test_api_similarity_and_catalog(stores, client, tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    _library(lib)
    monkeypatch.setenv("AUDIOTHECA_LIBRARY_ROOTS", str(lib))
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert client.put("/api/samples/similarity/roots", json={"roots": [str(outside)]}).status_code in (400, 403)
    assert client.put("/api/samples/similarity/roots", json={"roots": [str(lib)]}).status_code == 200
    assert client.post("/api/samples/similarity/index", json={}).json()["count"] == 9
    found = client.get("/api/samples/similar", params={"path": str(lib / "hats/hat0.wav"), "limit": 2}).json()
    assert [r["name"][:3] for r in found["results"]] == ["hat", "hat"]
    assert client.get("/api/samples/similar", params={"path": str(outside / "x.wav")}).status_code in (400, 403)

    _seed_local()
    bundle = client.post("/api/catalog/export", json={"name": "Mine"}).json()
    assert bundle["signature"]["alg"] == "ed25519"
    assert client.post("/api/catalog/preview", json={"bundle": bundle}).json()["changes"] == 0
    other = _bundle([{"company": "Bolt", "keywords": ["bolt"]}])
    assert client.post("/api/catalog/import", json={"bundle": other}).json()["vendor_rules"] == 1
    assert client.post("/api/catalog/subscriptions", json={"url": "http://x.example/c.json"}).status_code == 400
    assert client.get("/api/catalog").json()["local"]["vendor_rules"] == 2
