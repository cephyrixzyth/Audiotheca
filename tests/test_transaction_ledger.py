from __future__ import annotations

from pathlib import Path

from audiotheca.transaction_ledger import LEDGER_PATH, guarded_move, new_batch_id, rollback_batch


def test_guarded_move_and_rollback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "audiotheca.transaction_ledger.LEDGER_PATH",
        tmp_path / "ledger.jsonl",
    )
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("payload", encoding="utf-8")
    batch_id = new_batch_id()

    ok, err = guarded_move(src, dst, batch_id=batch_id, op="test")
    assert ok is True
    assert err is None
    assert dst.is_file()
    assert not src.exists()

    result = rollback_batch(batch_id, dry_run=False)
    assert result["ok"] is True
    assert src.is_file()
    assert not dst.exists()


def test_rollback_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "audiotheca.transaction_ledger.LEDGER_PATH",
        tmp_path / "ledger.jsonl",
    )
    src = tmp_path / "a.txt"
    dst = tmp_path / "b.txt"
    src.write_text("x", encoding="utf-8")
    batch_id = new_batch_id()
    guarded_move(src, dst, batch_id=batch_id, op="test")

    preview = rollback_batch(batch_id, dry_run=True)
    assert preview["ok"] is True
    assert dst.is_file()
    assert not src.exists()
