from __future__ import annotations

import json
from pathlib import Path

import pytest

import job_control as jc
from scan_options import ScanOptions, apply_staging_paths


def test_phase_checkpoint_pauses_and_continues(tmp_path, monkeypatch):
    control = tmp_path / "control.json"
    monkeypatch.setenv("AUDIOTHECA_CONTROL_FILE", str(control))
    control.write_text(json.dumps({"command": "pause"}), encoding="utf-8")

    import threading
    import time

    def _continue_later() -> None:
        time.sleep(0.2)
        control.write_text(json.dumps({"command": "continue"}), encoding="utf-8")

    threading.Thread(target=_continue_later, daemon=True).start()
    jc.phase_checkpoint("test_phase", "Test phase", pause_between_phases=False)


def test_phase_stop_raises(tmp_path, monkeypatch):
    control = tmp_path / "control.json"
    monkeypatch.setenv("AUDIOTHECA_CONTROL_FILE", str(control))
    control.write_text(json.dumps({"command": "stop"}), encoding="utf-8")
    with pytest.raises(jc.PhaseStopRequested):
        jc.phase_checkpoint("test_phase", "Test phase", pause_between_phases=False)


def test_cooperative_pause_mid_phase(tmp_path, monkeypatch):
    control = tmp_path / "control.json"
    monkeypatch.setenv("AUDIOTHECA_CONTROL_FILE", str(control))
    control.write_text(json.dumps({"command": "pause"}), encoding="utf-8")

    import threading
    import time

    def _continue_later() -> None:
        time.sleep(0.2)
        control.write_text(json.dumps({"command": "continue"}), encoding="utf-8")

    threading.Thread(target=_continue_later, daemon=True).start()
    jc.cooperative_checkpoint("parallel_scan", "Phase 1b - Parallel scan")


def test_pause_between_phases_steps(tmp_path, monkeypatch):
    control = tmp_path / "control.json"
    monkeypatch.setenv("AUDIOTHECA_CONTROL_FILE", str(control))
    control.write_text(json.dumps({"command": "run"}), encoding="utf-8")

    import threading
    import time

    def _continue_later() -> None:
        time.sleep(0.2)
        control.write_text(json.dumps({"command": "continue"}), encoding="utf-8")

    threading.Thread(target=_continue_later, daemon=True).start()
    jc.phase_checkpoint("phase_a", "Phase A", pause_between_phases=True)


def test_scan_options_skip_and_staging(tmp_path):
    opts = ScanOptions.from_dict(
        {
            "pause_between_phases": True,
            "skip_phases": ["archive_peek", "scene_peek"],
            "staging_root": str(tmp_path / "staging"),
            "extra_scan_roots": [r"Z:\other"],
        }
    )
    assert opts.skip("archive_peek")
    assert not opts.skip("duplicates")

    class FakeEngine:
        delete_candidates_dir = Path("x")
        quarantine_dir = Path("y")
        logger = __import__("logging").getLogger("test")

    engine = FakeEngine()
    apply_staging_paths(engine, opts)
    assert engine.delete_candidates_dir == tmp_path / "staging" / "_delete-canidates"
