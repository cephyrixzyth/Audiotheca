"""Regression: scan tree must not crash when probing plugin binaries."""

from pathlib import Path

import pytest

from main import DeduplicationEngine


@pytest.fixture
def engine(tmp_path):
    return DeduplicationEngine(tmp_path, dry_run=True, max_workers=1)


def test_scan_tree_vst3_without_name_error(engine, tmp_path):
    plugin_dir = tmp_path / "Product"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.vst3").write_bytes(b"MZ" + b"\x00" * 64)

    info = engine._scan_tree(plugin_dir)

    assert info["size"] >= 0
