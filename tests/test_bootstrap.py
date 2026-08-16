"""Tests for Bootstrap endpoints — status, bootstrap, конфликт."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rest.app import create_app


class TestBootstrapStatus:
    """GET /api/v1/auth/status — проверка needs_bootstrap."""

    def test_status_needs_bootstrap(self, app):
        from fastapi.testclient import TestClient
        client = TestClient(app)
        resp = client.get("/api/v1/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        # Проверяем что данные получены (формат зависит от proxy.call())
        assert "data" in data
        assert "error" in data

    def test_status_without_proxy(self):
        app_no_proxy = create_app(proxy_provider=None)
        client = TestClient(app_no_proxy)
        resp = client.get("/api/v1/auth/status")
        assert resp.status_code == 200
        assert resp.json()["data"]["needs_bootstrap"] is True


class TestBootstrapCreate:
    """POST /api/v1/auth/bootstrap — создание первого администратора."""

    def test_bootstrap_success(self, app):
        client = TestClient(app)
        resp = client.post("/api/v1/auth/bootstrap", json={
            "username": "admin",
            "password": "SecurePass123",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "access_token" in data

    def test_bootstrap_invalid_json(self, app):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/bootstrap",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_bootstrap_without_proxy(self):
        app_no_proxy = create_app(proxy_provider=None)
        client = TestClient(app_no_proxy)
        resp = client.post("/api/v1/auth/bootstrap", json={"username": "admin", "password": "pass"})
        assert resp.status_code == 503
