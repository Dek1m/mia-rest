"""Tests for RestConfig.from_env."""
from __future__ import annotations

from rest.config import RestConfig


def _clear_rest_env(monkeypatch: object) -> None:
    import os

    for key in list(os.environ):
        if key.startswith("MIA_REST_"):
            monkeypatch.delenv(key, raising=False)  # type: ignore[attr-defined]


def test_from_env_defaults(monkeypatch) -> None:
    _clear_rest_env(monkeypatch)
    cfg = RestConfig.from_env()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8080
    assert cfg.bind is True
    assert cfg.cors_origins == []
    assert cfg.spa_origins == ["http://localhost:5173"]
    assert cfg.max_body_bytes == 1_048_576
    assert cfg.docs is False


def test_from_env_overrides(monkeypatch) -> None:
    _clear_rest_env(monkeypatch)
    monkeypatch.setenv("MIA_REST_HOST", "0.0.0.0")
    monkeypatch.setenv("MIA_REST_PORT", "9090")
    monkeypatch.setenv("MIA_REST_BIND", "false")
    monkeypatch.setenv("MIA_REST_CORS_ORIGINS", "http://a.example, http://b.example")
    monkeypatch.setenv("MIA_REST_MAX_BODY_BYTES", "2048")
    monkeypatch.setenv("MIA_REST_DOCS", "true")
    cfg = RestConfig.from_env()
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9090
    assert cfg.bind is False
    assert cfg.cors_origins == ["http://a.example", "http://b.example"]
    assert cfg.max_body_bytes == 2048
    assert cfg.docs is True
