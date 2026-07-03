from __future__ import annotations

from progress import PhaseProgress


def test_phase_progress_unicode_detail(capsys, monkeypatch):
    monkeypatch.delenv("AUDIOTHECA_PROGRESS_FILE", raising=False)
    monkeypatch.delenv("AUDIOTHECA_CONTROL_FILE", raising=False)

    progress = PhaseProgress("Phase test", 1, "item")
    progress.update(1, detail="Cyrillic \u0421ample")

    captured = capsys.readouterr()
    assert "ample" in captured.out
