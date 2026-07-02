"""Tests for SearXNG search helper (no live instance required)."""

from __future__ import annotations

import argparse
import json

import pytest

from scripts import searx_search as ss


def test_presets_include_space_recovery():
    assert "space-recovery" in ss.PRESETS
    assert "vendor" in ss.PRESETS


def test_build_query_preset():
    args = argparse.Namespace(preset="vendor", arg=["8Dio"], query=[])
    q = ss.build_query(args)
    assert "8Dio" in q
    assert "vendor" in q.lower() or "library" in q.lower()


def test_compact_results_shape():
    data = {
        "query": "test",
        "results": [
            {"title": "A", "url": "https://a.test", "content": "snippet", "engine": "duckduckgo"},
        ],
    }
    out = ss.compact_results(data, limit=5)
    assert out["ok"] is True
    assert out["count"] == 1
    assert out["results"][0]["url"] == "https://a.test"


def test_ping_unreachable():
    status = ss.ping(base_url="http://127.0.0.1:59999", timeout=0.5)
    assert status["ok"] is False
    assert "hint" in status
