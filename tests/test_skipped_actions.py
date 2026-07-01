from __future__ import annotations

from api import skipped_actions


def test_build_rescan_options_includes_targets():
    opts = skipped_actions.build_rescan_options(["Z:\\a\\Item1", "Z:\\b\\Item2"])
    assert opts["target_paths"] == ["Z:\\a\\Item1", "Z:\\b\\Item2"]
    assert "duplicates" in opts["skip_phases"]
    assert opts["invalidate_cache_paths"] == ["Z:\\a\\Item1", "Z:\\b\\Item2"]
