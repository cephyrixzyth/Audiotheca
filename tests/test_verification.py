"""Tests for Phase 3.5 verification: scorecard and QA findings."""

from pathlib import Path

import pytest

from audiotheca.verification import (
    build_scorecard,
    find_destination_collisions,
    find_suspicious_keeps,
    find_unverified_db_vendors,
    find_vendor_candidates,
    run_verification,
)
from main import DeduplicationEngine
from scan_options import SKIPPABLE_PHASES, ScanOptions


@pytest.fixture
def engine(tmp_path):
    return DeduplicationEngine(tmp_path, dry_run=True, max_workers=1)


def _item(name, *, company=None, confidence="UNKNOWN", base=None, size=10**8):
    return {
        "original_name": name,
        "path": Path(f"/lib/{name}"),
        "company": company,
        "id_confidence": confidence,
        "base_name": base or name.lower().replace(" ", ""),
        "size": size,
        "is_dir": True,
        "is_tonex": False,
        "source_bin": "plugins",
    }


class TestScorecard:
    def test_rates(self, engine):
        items = [
            _item("Serum", company="Xfer", confidence="CONFIRMED"),
            _item("Guess Pack", company="Maybe Co", confidence="TENTATIVE"),
            _item("Total Mystery"),
            _item("Other Mystery"),
        ]
        plan = [
            {"status": "READY", "destination": "/dest/a", "original_name": "Serum"},
            {"status": "NEEDS REVIEW", "destination": "/dest/b", "original_name": "Guess Pack"},
        ]
        score = build_scorecard(
            items,
            duplicate_groups=[],
            investigation_plan=[{"bucket": "_unknown_vendor"}],
            restructure_plan=plan,
            build_dedup_key=engine.build_dedup_key,
        )
        assert score["total_items"] == 4
        assert score["identified_confirmed"] == 1
        assert score["identified_tentative"] == 1
        assert score["identified_unknown"] == 2
        assert score["identification_rate_pct"] == 50.0
        assert score["route_ready_pct"] == 50.0
        assert score["investigation_buckets"] == {"_unknown_vendor": 1}

    def test_empty_run_is_100_pct(self, engine):
        score = build_scorecard(
            [],
            duplicate_groups=[],
            investigation_plan=[],
            restructure_plan=[],
            build_dedup_key=engine.build_dedup_key,
        )
        assert score["identification_rate_pct"] == 100.0


class TestVendorCandidates:
    def test_cluster_of_unknowns_surfaces_token(self):
        items = [
            _item("Soundtoys Decapitator"),
            _item("Soundtoys EchoBoy"),
            _item("Soundtoys PrimalTap"),
        ]
        findings = find_vendor_candidates(items)
        assert len(findings) == 1
        assert findings[0]["check"] == "VENDOR_CANDIDATE"
        assert findings[0]["subject"] == "soundtoys"

    def test_generic_tokens_ignored(self):
        items = [_item(f"Sample Pack {i}") for i in range(5)]
        assert find_vendor_candidates(items) == []

    def test_identified_items_not_clustered(self):
        items = [
            _item(f"Soundtoys Plugin {i}", company="Soundtoys", confidence="CONFIRMED")
            for i in range(5)
        ]
        assert find_vendor_candidates(items) == []

    def test_two_items_below_cluster_minimum(self):
        items = [_item("Soundtoys A"), _item("Soundtoys B")]
        assert find_vendor_candidates(items) == []


class TestDestinationCollisions:
    def test_two_items_same_destination(self):
        plan = [
            {"destination": "/dest/Vendor/Product", "original_name": "Copy One",
             "current_path": "/a", "investigation_bucket": ""},
            {"destination": "/dest/Vendor/Product", "original_name": "Copy Two",
             "current_path": "/b", "investigation_bucket": ""},
        ]
        findings = find_destination_collisions(plan)
        assert len(findings) == 1
        assert findings[0]["check"] == "DEST_COLLISION"

    def test_investigation_rows_excluded(self):
        plan = [
            {"destination": "/inv/x", "original_name": "A", "current_path": "/a",
             "investigation_bucket": "_unknown_vendor"},
            {"destination": "/inv/x", "original_name": "B", "current_path": "/b",
             "investigation_bucket": "_unknown_vendor"},
        ]
        assert find_destination_collisions(plan) == []

    def test_same_name_twice_not_collision(self):
        plan = [
            {"destination": "/dest/x", "original_name": "Same", "current_path": "/a",
             "investigation_bucket": ""},
            {"destination": "/dest/x", "original_name": "Same", "current_path": "/b",
             "investigation_bucket": ""},
        ]
        assert find_destination_collisions(plan) == []


class TestUnverifiedDbVendors:
    def test_confirmed_vendor_missing_from_db(self):
        items = [
            _item("Cool Plugin", company="Obscure Devs", confidence="CONFIRMED"),
            _item("Cool Plugin 2", company="Obscure Devs", confidence="CONFIRMED"),
        ]
        findings = find_unverified_db_vendors(items, {"Xfer": {"xfer"}})
        assert len(findings) == 1
        assert findings[0]["subject"] == "Obscure Devs"
        assert "2 item(s)" in findings[0]["detail"]

    def test_db_vendor_not_flagged(self):
        items = [_item("Serum", company="Xfer", confidence="CONFIRMED")]
        assert find_unverified_db_vendors(items, {"Xfer": {"xfer"}}) == []


class TestSuspiciousKeeps:
    def test_small_keeper_flagged(self):
        small = {"original_name": "v2 stub", "path": "/a", "size": 10 * 1024 * 1024}
        large = {"original_name": "v1 full", "path": "/b", "size": 900 * 1024 * 1024}
        groups = [
            {"dedup_key": "vendor|product", "recommended_keep": small, "items": [small, large]}
        ]
        findings = find_suspicious_keeps(groups)
        assert len(findings) == 1
        assert findings[0]["check"] == "SUSPICIOUS_KEEP"

    def test_reasonable_keeper_not_flagged(self):
        keep = {"original_name": "v2", "path": "/a", "size": 800 * 1024 * 1024}
        other = {"original_name": "v1", "path": "/b", "size": 900 * 1024 * 1024}
        groups = [{"dedup_key": "k", "recommended_keep": keep, "items": [keep, other]}]
        assert find_suspicious_keeps(groups) == []


class TestRunVerification:
    def test_full_pass_returns_scorecard_and_findings(self, engine):
        items = [
            _item("Soundtoys Decapitator"),
            _item("Soundtoys EchoBoy"),
            _item("Soundtoys PrimalTap"),
            _item("Serum", company="Xfer Records", confidence="CONFIRMED"),
        ]
        scorecard, findings = run_verification(
            items,
            duplicate_groups=[],
            investigation_plan=[],
            restructure_plan=[],
            vendor_aliases=engine.vendor_aliases,
            build_dedup_key=engine.build_dedup_key,
        )
        assert scorecard["findings_total"] == len(findings)
        checks = {f["check"] for f in findings}
        assert "VENDOR_CANDIDATE" in checks


class TestScanOptionsNewPhases:
    def test_new_phases_are_skippable(self):
        assert "malware_scan" in SKIPPABLE_PHASES
        assert "deep_identify" in SKIPPABLE_PHASES
        assert "verification" in SKIPPABLE_PHASES

    def test_from_dict_accepts_new_phases(self):
        options = ScanOptions.from_dict({"skip_phases": ["deep_identify", "verification"]})
        assert options.skip("deep_identify")
        assert options.skip("verification")
