"""Tests for cross-platform OS lane routing."""

from pathlib import Path

import pytest

from audiotheca.platform_routing import (
    off_lane,
    os_status_label,
    platform_flags,
    prefix_destination,
)


class TestOffLane:
    def test_mac_only_on_windows_host(self):
        flags = {"has_windows": False, "has_mac": True, "has_linux": False, "has_assets": False}
        assert off_lane(flags, "windows") == "mac"

    def test_mac_only_on_mac_host_is_native(self):
        flags = {"has_windows": False, "has_mac": True, "has_linux": False, "has_assets": False}
        assert off_lane(flags, "mac") is None

    def test_linux_only_on_windows_host(self):
        flags = {"has_windows": False, "has_mac": False, "has_linux": True, "has_assets": False}
        assert off_lane(flags, "windows") == "linux"

    def test_linux_only_on_linux_host_is_native(self):
        flags = {"has_windows": False, "has_mac": False, "has_linux": True, "has_assets": False}
        assert off_lane(flags, "linux") is None

    def test_windows_only_on_linux_host(self):
        flags = {"has_windows": True, "has_mac": False, "has_linux": False, "has_assets": False}
        assert off_lane(flags, "linux") == "windows"

    def test_assets_stay_native(self):
        flags = {"has_windows": False, "has_mac": True, "has_linux": False, "has_assets": True}
        assert off_lane(flags, "windows") is None

    def test_cross_platform_bundle_stays_native(self):
        flags = {"has_windows": True, "has_mac": True, "has_linux": False, "has_assets": False}
        assert off_lane(flags, "linux") is None


class TestPrefixDestination:
    def test_prefixes_section_vendor_path(self, tmp_path: Path):
        root = tmp_path
        dest = root / "VST Plugins" / "Xfer" / "Serum"
        prefixed, rel = prefix_destination(
            root,
            dest,
            "VST Plugins/Xfer/Serum",
            "mac",
        )
        assert prefixed == root / "_mac" / "VST Plugins" / "Xfer" / "Serum"
        assert rel == "_mac/VST Plugins/Xfer/Serum"

    def test_no_prefix_for_native_lane(self, tmp_path: Path):
        root = tmp_path
        dest = root / "VST Plugins" / "Xfer" / "Serum"
        same, rel = prefix_destination(root, dest, "VST Plugins/Xfer/Serum", None)
        assert same == dest
        assert rel == "VST Plugins/Xfer/Serum"


class TestOsStatusLabel:
    def test_off_lane_mac(self):
        flags = platform_flags({"has_mac": True})
        assert os_status_label(flags, "windows") == "OFF_LANE_MAC"

    def test_native_compatible(self):
        flags = platform_flags({"has_windows": True})
        assert os_status_label(flags, "windows") == "NATIVE_COMPATIBLE"


class TestComputeDestinationIntegration:
    def test_mac_item_routes_under_mac_lane(self, tmp_path: Path):
        from main import DeduplicationEngine

        engine = DeduplicationEngine(tmp_path, dry_run=True, max_workers=1)
        item = {
            "path": tmp_path / "item",
            "is_dir": True,
            "company": "Xfer",
            "original_name": "Serum",
            "source_bin": "VST Plugins",
            "is_tonex": False,
            "id_method": "TEST",
            "id_confidence": "CONFIRMED",
            "platform_lane": "mac",
            "skip_investigation": True,
        }
        dest, rel, status, bucket = engine.compute_destination(item)
        assert bucket == ""
        assert status == "READY"
        assert rel.startswith("_mac/VST Plugins/Xfer")
        assert "_mac" in dest.parts
        assert dest.name == "Serum"

    def test_skip_quarantine_leaves_native_path(self, tmp_path: Path):
        from main import DeduplicationEngine

        engine = DeduplicationEngine(tmp_path, dry_run=True, max_workers=1)
        engine.scan_options.skip_phases.add("quarantine")
        item = {
            "path": tmp_path / "item",
            "is_dir": True,
            "company": "Xfer",
            "original_name": "Serum",
            "source_bin": "VST Plugins",
            "is_tonex": False,
            "id_method": "TEST",
            "id_confidence": "CONFIRMED",
            "platform_lane": "mac",
            "skip_investigation": True,
        }
        dest, rel, _status, _bucket = engine.compute_destination(item)
        assert "_mac" not in rel
        assert dest == tmp_path / "VST Plugins" / "Xfer" / "Serum"
