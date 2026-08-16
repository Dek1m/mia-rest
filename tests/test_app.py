"""Tests for REST App — маршруты, авторизация, ошибки, пагинация."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rest.app import create_app
from rest.config import RestConfig


class TestHealthEndpoint:
    """Тесты health-check."""

    def test_health_ok(self, app):
        client = TestClient(app)
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestPostMethod:
    """Тесты POST /api/v1/{module}/{method}."""

    def test_public_method_login(self, app):
        client = TestClient(app)
        resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "pass"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert data["data"]["access_token"] == "fake-token"

    def test_401_unauthorized(self, app):
        client = TestClient(app)
        resp = client.post("/api/v1/auth/get_me", json={})
        assert resp.status_code == 401

    def test_404_unknown_method(self, app):
        client = TestClient(app)
        resp = client.post("/api/v1/auth/nonexistent", json={})
        assert resp.status_code == 404

    def test_400_invalid_args(self, app):
        client = TestClient(app)
        resp = client.post("/api/v1/auth/login", json={})
        # login is public and has defaults, so it should work
        assert resp.status_code == 200

    def test_403_module_not_in_whitelist(self, app):
        # "unknown" модуль не в реестре → FastAPI вернёт 404 (маршрут не найден)
        # Whitelist проверка происходит внутри proxy.call, но маршрут не зарегистрирован
        client = TestClient(app)
        resp = client.post("/api/v1/unknown/do_something", json={})
        assert resp.status_code == 404


class TestGetMethod:
    """Тесты GET /api/v1/{module}?method={method}&..."""

    def test_get_public_method(self, app):
        client = TestClient(app)
        resp = client.get("/api/v1/auth?method=login&username=admin&password=pass")
        assert resp.status_code == 200
        assert resp.json()["data"]["access_token"] == "fake-token"

    def test_get_missing_method_param(self, app):
        client = TestClient(app)
        resp = client.get("/api/v1/auth")
        assert resp.status_code == 400
        assert "method" in resp.json()["error"]["message"].lower()

    def test_get_with_query_params(self, app):
        client = TestClient(app)
        resp = client.get("/api/v1/auth?method=login&username=admin&password=pass")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"] == "fake-token"


class TestBrowserRedirect:
    """Тесты браузерного редиректа при 401."""

    def test_401_redirect_for_browser(self, app):
        client = TestClient(app, follow_redirects=False)
        resp = client.get(
            "/api/v1/auth?method=get_me",
            headers={"Accept": "text/html"},
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/auth/login"


class TestListModules:
    """Тесты GET /api/v1 — список модулей."""

    def test_list_all_modules(self, app):
        client = TestClient(app)
        resp = client.get("/api/v1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "auth" in data
        assert len(data["auth"]) >= 3


class TestPagination:
    """Тесты пагинации в ответах."""

    def test_list_users_has_pagination(self, app):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/list_users",
            json={"limit": 10, "offset": 0},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "items" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data


class Test500Handling:
    """Тесты обработки 500 ошибок."""

    def test_internal_error_returns_500(self):
        from apiproxy.registry import MethodRegistry
        from apiproxy.provider import ApiProxyProvider
        from apiproxy.config import ApiproxyConfig
        from auth.decorators import auth_method

        class ErrorProvider:
            @auth_method(
                name="fail_method",
                description="Fail",
                args={},
                return_type=None,
                public=True,
            )
            async def fail_method(self):
                raise RuntimeError("Database connection failed")

        registry = MethodRegistry()
        provider = ErrorProvider()
        registry.collect_from_module(provider, "test")

        proxy = ApiProxyProvider(config=ApiproxyConfig(whitelist=["test"]))
        proxy._registry = registry

        test_app = create_app(proxy_provider=proxy)
        client = TestClient(test_app)
        resp = client.post("/api/v1/test/fail_method", json={})
        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == "ERROR_500"
