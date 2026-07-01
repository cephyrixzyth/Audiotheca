from __future__ import annotations

import pytest
from fastapi import HTTPException

from api import security


def test_normalize_stamp_valid():
    assert security.normalize_stamp("20260611_0208") == "20260611_0208"


def test_normalize_stamp_invalid():
    with pytest.raises(ValueError):
        security.normalize_stamp("../etc/passwd")


def test_parse_dry_run_bool_only():
    assert security.parse_dry_run(True) is True
    assert security.parse_dry_run(False) is False
    assert security.parse_dry_run(None, default=True) is True
    with pytest.raises(HTTPException):
        security.parse_dry_run("false")


def test_sanitize_relative_dest_rejects_dotdot(tmp_path, monkeypatch):
    library = tmp_path / "lib"
    library.mkdir()
    monkeypatch.setattr(security, "library_roots", lambda: [library])
    with pytest.raises(HTTPException):
        security.sanitize_relative_dest("../../outside", library)
    with pytest.raises(ValueError):
        security._sanitize_relative_dest("../../outside", library)


def test_safe_report_path_blocks_traversal(tmp_path):
    base = tmp_path / "reports"
    base.mkdir()
    with pytest.raises(HTTPException):
        security.safe_report_path(base.resolve(), "../../outside.txt")


def test_verify_token(api_token):
    assert security.verify_token(api_token)
    assert not security.verify_token("wrong-token")


def test_redact_path():
    assert security.redact_path(r"Z:\a\b\c\ProductName").endswith("c/ProductName")
