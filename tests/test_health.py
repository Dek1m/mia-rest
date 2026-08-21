"""Tests for /health and /ready."""
from __future__ import annotations

from fastapi.testclient import TestClient

from rest.config import RestConfig
from rest.factory import create_app


def test_health_ok(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_ok(client) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_without_proxy() -> None:
    app = create_app(RestConfig(bind=False), proxy=None, log=None)
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["data"] is None
    assert body["error"]["status_code"] == 503
    assert body["meta"]["client_type"] == "rest"
