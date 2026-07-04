from __future__ import annotations

from progress import PhaseProgress


def test_phase_progress_pulse_emits_heartbeat(monkeypatch):
    events: list[dict] = []

    def capture(payload: dict) -> None:
        events.append(payload)

    monkeypatch.setattr("progress._emit_progress_event", capture)
    monkeypatch.delenv("AUDIOTHECA_PROGRESS_FILE", raising=False)

    progress = PhaseProgress("Phase test", 10, "section")
    progress.update(3, detail="three done")
    progress.pulse(detail="still listing…")

    progress_events = [event for event in events if event["type"] == "phase_progress"]
    assert len(progress_events) == 2
    pulse = progress_events[-1]
    assert pulse["type"] == "phase_progress"
    assert pulse["done"] == 3
    assert pulse["total"] == 10
    assert pulse["heartbeat"] is True
    assert pulse["detail"] == "still listing…"


def test_phase_progress_unicode_detail(capsys, monkeypatch):
    monkeypatch.delenv("AUDIOTHECA_PROGRESS_FILE", raising=False)
    monkeypatch.delenv("AUDIOTHECA_CONTROL_FILE", raising=False)

    progress = PhaseProgress("Phase test", 1, "item")
    progress.update(1, detail="Cyrillic \u0421ample")

    captured = capsys.readouterr()
    assert "ample" in captured.out
