from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Windows-style library roots used in tests and CI (logical validation on Linux).
os.environ.setdefault(
    "AUDIOTHECA_LIBRARY_ROOTS",
    r"Z:\_software\_audio,Z:\test,Z:\lib,Z:\a",
)

from api import security
from api.server import app


@pytest.fixture
def api_token(monkeypatch, tmp_path):
    token = "test-token-for-pytest-only"
    monkeypatch.setattr(security, "TOKEN_PATH", tmp_path / ".api_token")
    monkeypatch.setenv("AUDIOTHECA_API_TOKEN", token)
    return token


@pytest.fixture
def client(api_token):
    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {api_token}"})
    return client
