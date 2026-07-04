"""Tests for contextual AI lookup subsystem."""

from __future__ import annotations

from pathlib import Path

import pytest

from audiotheca.ai_lookup.cache import LookupCache
from audiotheca.ai_lookup.disambiguation import LookupResult
from audiotheca.ai_lookup.engine import LookupEngine, needs_ai_lookup
from audiotheca.ai_lookup.nfo_reader import parse_release_text, read_release_metadata
from audiotheca.ai_lookup.providers.stub import StubLookupProvider
from audiotheca.ai_lookup.telemetry import build_telemetry, relative_path


def _item(name: str, path: Path, **kwargs) -> dict:
    return {
        "original_name": name,
        "path": path,
        "source_bin": "plugins",
        "id_method": "NONE",
        "id_confidence": "UNKNOWN",
        "size": 1024,
        "is_dir": True,
        **kwargs,
    }


class TestNeedsAiLookup:
    def test_unknown_qualifies(self):
        assert needs_ai_lookup(_item("Mystery", Path("/x/Mystery")))

    def test_confirmed_skipped(self):
        item = _item("Serum", Path("/x/Serum"), company="Xfer", id_confidence="CONFIRMED")
        assert not needs_ai_lookup(item)


class TestTelemetrySanitization:
    def test_relative_path_strips_user_home(self, tmp_path):
        root = tmp_path / "library"
        target = root / "plugins" / "Vendor Pack"
        target.mkdir(parents=True)
        rel = relative_path(target, root)
        assert rel == "plugins/Vendor Pack"
        assert "Users" not in rel

    def test_build_telemetry_no_absolute_paths(self, tmp_path):
        root = tmp_path / "library"
        target = root / "Unknown Product"
        target.mkdir(parents=True)
        item = _item("Unknown Product", target)
        payload = build_telemetry(item, root=root)
        assert payload["relative_path"] == "Unknown Product"
        assert "content_hash" in payload
        assert str(root) not in str(payload)


class TestNfoParsing:
    def test_parse_release_group_and_url(self):
        text = """
        Release Group: R2R
        Date: 2024-03-15
        Product: Super Synth
        Visit https://example.com/product
        """
        meta = parse_release_text(text)
        assert meta["release_group"] == "R2R"
        assert meta["product_hint"] == "Super Synth"
        assert meta["source_url"] == "https://example.com/product"

    def test_read_release_metadata_from_nfo(self, tmp_path):
        folder = tmp_path / "SceneHash-ABC"
        folder.mkdir()
        (folder / "release.nfo").write_text("Release Group: ARCADiA\nProduct: Mega Drums", encoding="utf-8")
        meta = read_release_metadata(folder)
        assert meta["release_group"] == "ARCADiA"
        assert meta["product_hint"] == "Mega Drums"


class TestLookupCache:
    def test_put_and_get(self, tmp_path):
        cache = LookupCache(cache_dir=tmp_path / "cache")
        result = LookupResult(
            lookup_id="abc123",
            content_hash="hash001",
            status="hit",
            confidence=0.85,
            reasoning="test",
            vendor="Acme Audio",
        )
        cache.put(result)
        loaded = cache.get("hash001")
        assert loaded is not None
        assert loaded.vendor == "Acme Audio"


class TestStubProvider:
    def test_stub_returns_mock_result(self):
        provider = StubLookupProvider()
        raw = provider.lookup({"original_name": "Dark Strings", "name_tokens": ["dark", "strings"]})
        assert raw["confidence"] > 0
        assert raw["pending_verification"] is True

    def test_engine_lookup_pending(self, tmp_path):
        root = tmp_path / "library"
        target = root / "Mystery Pack"
        target.mkdir(parents=True)
        engine = LookupEngine(root=root, cache=LookupCache(cache_dir=tmp_path / "cache"))
        result = engine.lookup_item(_item("Mystery Pack", target))
        assert result.lookup_id
        assert result.relative_path == "Mystery Pack"
        assert result.status in {"pending", "hit"}
