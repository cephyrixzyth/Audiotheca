from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

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
