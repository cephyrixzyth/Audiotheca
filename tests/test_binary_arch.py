from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from audiotheca import binary_arch
from audiotheca.binary_arch import inspect_pe, merge_arch_flags


class _FakePE:
    def __init__(self, machine: int) -> None:
        self.FILE_HEADER = SimpleNamespace(Machine=machine)

    def close(self) -> None:
        return None


def test_inspect_pe_x64(tmp_path, monkeypatch):
    monkeypatch.setattr(binary_arch, "HAS_PEFILE", True)

    def fake_pe(_path: str, fast_load: bool = True) -> _FakePE:
        return _FakePE(0x8664)

    monkeypatch.setattr(binary_arch, "pefile", SimpleNamespace(PE=fake_pe))
    result = inspect_pe(tmp_path / "plugin.dll")
    assert result["architectures"] == ["x64"]
    assert result["legacy_32bit"] is False


def test_inspect_pe_x86_flags_legacy(tmp_path, monkeypatch):
    monkeypatch.setattr(binary_arch, "HAS_PEFILE", True)

    def fake_pe(_path: str, fast_load: bool = True) -> _FakePE:
        return _FakePE(0x014C)

    monkeypatch.setattr(binary_arch, "pefile", SimpleNamespace(PE=fake_pe))
    result = inspect_pe(tmp_path / "legacy.dll")
    assert result["architectures"] == ["x86"]
    assert result["legacy_32bit"] is True


def test_merge_arch_flags():
    info = {"arch_x86": False, "arch_x64": False, "arch_arm64": False, "legacy_32bit": False}
    merge_arch_flags(info, {"architectures": ["x86"], "legacy_32bit": True})
    assert info["arch_x86"] is True
    assert info["legacy_32bit"] is True


def test_inspect_pe_without_pefile(tmp_path, monkeypatch):
    monkeypatch.setattr(binary_arch, "HAS_PEFILE", False)
    result = inspect_pe(tmp_path / "missing.dll")
    assert result["architectures"] == []
    assert "pefile unavailable" in result.get("error", "")
