"""HTTP-сценарии RPC, auth, envelope, openapi, cors, metrics, логи."""
from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from rest import RestModule
from rest.config import RestConfig
from rest.factory import create_app
from rest.metrics import rest_http_request_duration_seconds, rest_http_requests_total


class TestLoginAndMeta:
    def test_login_200_with_meta(self, client) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "secret"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["error"] is None
        assert body["data"]["access_token"] == "fake-token"
        assert body["meta"]["client_type"] == "rest"
        assert body["meta"]["request_id"]
        assert isinstance(body["meta"]["duration_ms"], int)

    def test_create_returns_200_not_201(self, client) -> None:
        response = client.post(
            "/api/v1/auth/create_user",
            json={"username": "neo", "password": "x"},
            headers={"Authorization": "Bearer tok"},
        )
        assert response.status_code == 200
        assert response.status_code != 201
        assert response.json()["data"]["username"] == "neo"

    def test_pagination_as_is(self, client) -> None:
        response = client.post(
            "/api/v1/llm/agents",
            json={"page": 2, "page_size": 5},
            headers={"Authorization": "Bearer tok"},
        )
        assert response.status_code == 200
        assert response.json()["data"] == {
            "items": [{"id": "a1", "name": "agent"}],
            "page": 2,
            "page_size": 5,
            "total": 1,
        }

    def test_client_type_header_ignored(self, client) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "x"},
            headers={"X-Client-Type": "cli"},
        )
        assert response.json()["meta"]["client_type"] == "rest"

    def test_request_id_echo(self, client) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "x"},
            headers={"X-Request-Id": "abc-123"},
        )
        assert response.headers["x-request-id"] == "abc-123"
        assert response.json()["meta"]["request_id"] == "abc-123"


class TestBearer:
    def test_get_me_401_www_authenticate(self, client) -> None:
        response = client.post("/api/v1/auth/get_me", json={})
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["error"]["status_code"] == 401

    def test_non_bearer_is_anonymous(self, client) -> None:
        response = client.post(
            "/api/v1/auth/get_me",
            json={},
            headers={"Authorization": "Basic abc"},
        )
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_bearer_without_token_is_anonymous(self, client) -> None:
        response = client.post(
            "/api/v1/auth/get_me",
            json={},
            headers={"Authorization": "Bearer"},
        )
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_bearer_200(self, client, fake_proxy) -> None:
        response = client.post(
            "/api/v1/auth/get_me",
            json={},
            headers={"Authorization": "Bearer tok-1"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["username"] == "admin"
        assert fake_proxy.calls[-1][3] == "tok-1"


class TestErrors:
    def test_unknown_method_404(self, client) -> None:
        response = client.post("/api/v1/auth/nope", json={})
        assert response.status_code == 404
        assert response.json()["error"]["status_code"] == 404

    def test_unknown_module_http_matches_error_status(self, client) -> None:
        response = client.post("/api/v1/ghost/ping", json={})
        body = response.json()
        assert body["error"] is not None
        assert response.status_code == body["error"]["status_code"]
        assert response.status_code == 404

    def test_array_body_400_not_422(self, client) -> None:
        response = client.post("/api/v1/auth/login", json=[])
        assert response.status_code == 400
        assert response.status_code != 422
        assert response.json()["error"] is not None

    def test_garbage_json_400_not_422(self, client) -> None:
        response = client.post(
            "/api/v1/auth/login",
            content=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert response.status_code != 422
        assert response.json()["meta"]["client_type"] == "rest"

    def test_get_rpc_405(self, client) -> None:
        response = client.get("/api/v1/auth/login")
        assert response.status_code == 405
        body = response.json()
        assert "meta" not in body

    def test_empty_body_without_content_type_is_empty_kwargs(self, client, fake_proxy) -> None:
        response = client.post(
            "/api/v1/auth/get_me",
            content=b"",
            headers={"Authorization": "Bearer tok"},
        )
        assert response.status_code == 200
        assert fake_proxy.calls[-1][2] == {}

    def test_null_body_400_not_422(self, client) -> None:
        response = client.post(
            "/api/v1/auth/login",
            content=b"null",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert response.status_code != 422
        assert response.json()["error"] is not None

    def test_rpc_without_proxy_503(self) -> None:
        app = create_app(RestConfig(bind=False), proxy=None, log=None)
        with TestClient(app) as client:
            response = client.post("/api/v1/auth/login", json={"username": "a"})
        assert response.status_code == 503
        body = response.json()
        assert body["error"]["status_code"] == 503
        assert body["meta"]["client_type"] == "rest"

    def test_boom_500(self, client) -> None:
        response = client.post("/api/v1/auth/boom", json={})
        assert response.status_code == 500
        assert response.json()["error"]["status_code"] == 500

    def test_body_too_large_413(self, fake_proxy, fake_log) -> None:
        app = create_app(
            RestConfig(bind=False, max_body_bytes=64),
            fake_proxy,
            fake_log,
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                content=b"x" * 128,
                headers={"Content-Type": "application/json"},
            )
        assert response.status_code == 413
        assert response.json()["error"]["status_code"] == 413


class TestOpenApi:
    def test_docs_off_404_envelope(self, client) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 404
        body = response.json()
        assert body["error"] is not None
        assert body["meta"]["client_type"] == "rest"

    def test_docs_on_openapi3(self, fake_proxy, fake_log) -> None:
        app = create_app(RestConfig(bind=False, docs=True), fake_proxy, fake_log)
        with TestClient(app) as client:
            response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert spec["openapi"].startswith("3.")
        login = spec["paths"]["/api/v1/auth/login"]["post"]
        me = spec["paths"]["/api/v1/auth/get_me"]["post"]
        assert "security" not in login
        assert me["security"] == [{"bearerAuth": []}]
        assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"

    def test_docs_has_no_workspace_crud(self, fake_proxy, fake_log) -> None:
        app = create_app(RestConfig(bind=False, docs=True), fake_proxy, fake_log)
        with TestClient(app) as client:
            spec = client.get("/openapi.json").json()
        paths = spec["paths"]
        assert "/workspaces" not in paths
        assert all("workspace" not in path.lower() for path in paths)


class TestCors:
    def test_empty_origins_deny(self, client) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "a", "password": "b"},
            headers={"Origin": "http://evil.example"},
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers

    def test_allowed_origin_header(self, fake_proxy, fake_log) -> None:
        app = create_app(
            RestConfig(bind=False, cors_origins=["http://ok.example"]),
            fake_proxy,
            fake_log,
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "a", "password": "b"},
                headers={"Origin": "http://ok.example"},
            )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "http://ok.example"

    def test_unlisted_origin_not_echoed(self, fake_proxy, fake_log) -> None:
        app = create_app(
            RestConfig(bind=False, cors_origins=["http://ok.example"]),
            fake_proxy,
            fake_log,
        )
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "a", "password": "b"},
                headers={"Origin": "http://evil.example"},
            )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") != "http://evil.example"


class TestMetrics:
    def test_rpc_labels(self, client) -> None:
        before = rest_http_requests_total.labels(
            module="auth", function="login", status="200",
        )._value.get()
        client.post("/api/v1/auth/login", json={"username": "a", "password": "b"})
        after = rest_http_requests_total.labels(
            module="auth", function="login", status="200",
        )._value.get()
        assert after == before + 1
        hist = rest_http_request_duration_seconds.labels(
            module="auth", function="login", status="200",
        )
        assert hist._sum.get() >= 0

    def test_system_labels(self, client) -> None:
        before = rest_http_requests_total.labels(
            module="_system", function="health", status="200",
        )._value.get()
        client.get("/health")
        after = rest_http_requests_total.labels(
            module="_system", function="health", status="200",
        )._value.get()
        assert after == before + 1


class TestLogs:
    def test_no_password_values(self, client, fake_log) -> None:
        secret = "s3cret-password-value"
        client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": secret},
            headers={"Authorization": "Bearer super-secret-token"},
        )
        blob = json.dumps(fake_log.records)
        assert secret not in blob
        assert "super-secret-token" not in blob
        started = [r for r in fake_log.records if r[1] == "request_started"]
        assert started
        keys = started[-1][2]["args_keys"]
        assert "password" in keys
        assert "username" in keys


class TestSpaCookies:
    def test_spa_login_sets_host_cookies_strips_tokens(self, client) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "secret"},
            headers={"X-Albedo-Client": "spa", "Origin": "http://localhost:5173"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["error"] is None
        assert "access_token" not in body["data"]
        assert "refresh_token" not in body["data"]
        assert body["data"]["user_id"] == "user-1"
        cookies = response.headers.get_list("set-cookie")
        blob = "\n".join(cookies)
        assert "__Host-albedo_at=" in blob
        assert "__Host-albedo_rt=" in blob
        assert "Domain=" not in blob
        assert "samesite=lax" in blob.lower()
        assert "samesite=strict" in blob.lower()

    def test_cookie_without_spa_header_is_csrf(self, client) -> None:
        response = client.post(
            "/api/v1/auth/get_me",
            json={},
            headers={"Cookie": "__Host-albedo_at=tok"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_HEADER"

    def test_spa_origin_mismatch(self, client) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "a", "password": "b"},
            headers={"X-Albedo-Client": "spa", "Origin": "http://evil.example"},
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ORIGIN_MISMATCH"

    def test_spa_refresh_injects_cookie_ignores_body(self, client, fake_proxy) -> None:
        response = client.post(
            "/api/v1/auth/refresh_token",
            json={"refresh_token": "from-body"},
            headers={
                "X-Albedo-Client": "spa",
                "Origin": "http://localhost:5173",
                "Cookie": "__Host-albedo_rt=from-cookie",
            },
        )
        assert response.status_code == 200
        assert fake_proxy.calls[-1][2]["refresh_token"] == "from-cookie"
        assert fake_proxy.calls[-1][3] is None
        assert "access_token" not in response.json()["data"]

    def test_spa_refresh_reuse_clears_cookies(self, client) -> None:
        response = client.post(
            "/api/v1/auth/refresh_token",
            json={},
            headers={
                "X-Albedo-Client": "spa",
                "Origin": "http://localhost:5173",
                "Cookie": "__Host-albedo_rt=reuse",
            },
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "REUSE_DETECTED"
        blob = "\n".join(response.headers.get_list("set-cookie"))
        assert "__Host-albedo_at=" in blob
        assert "__Host-albedo_rt=" in blob
        assert "Max-Age=0" in blob

    def test_spa_logout_always_clears(self, client) -> None:
        response = client.post(
            "/api/v1/auth/logout",
            json={},
            headers={"X-Albedo-Client": "spa", "Origin": "http://localhost:5173"},
        )
        assert response.status_code == 200
        blob = "\n".join(response.headers.get_list("set-cookie"))
        assert "Max-Age=0" in blob
        assert "__Host-albedo_at=" in blob
        assert "__Host-albedo_rt=" in blob

    def test_machine_login_keeps_tokens(self, client) -> None:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "secret"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["access_token"] == "fake-token"
        assert not response.headers.get_list("set-cookie")


class TestAvatarGet:
    def test_avatar_without_cookie_401(self, client) -> None:
        response = client.get("/api/v1/auth/avatar")
        assert response.status_code == 401

    def test_avatar_bytes_nosniff_nostore(self, rest_config, fake_log) -> None:
        class _Auth:
            async def validate_token(self, token: str):
                assert token == "tok"
                return SimpleNamespace(user_id="u1")

            async def get_avatar_bytes(self, user_id: str):
                assert user_id == "u1"
                return b"\x89PNG", "image/png"

        class _Proxy:
            auth_provider = _Auth()

            async def call(self, *args, **kwargs):
                return {"data": None, "error": {"code": "ERROR_404", "message": "x", "status_code": 404}}

            def list_api(self, module_name=None):
                return []

        app = create_app(rest_config, _Proxy(), fake_log)
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/auth/avatar",
                headers={"Cookie": "__Host-albedo_at=tok"},
            )
        assert response.status_code == 200
        assert response.content == b"\x89PNG"
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "image/png" in response.headers["content-type"]


class TestRestModuleContract:
    def test_no_api_meta_no_register_schema_no_task(self) -> None:
        module = RestModule(config=RestConfig(bind=False))
        assert module.meta.dependencies == ["log", "apiproxy"]
        assert not hasattr(module, "_api_meta")
        assert not hasattr(RestModule, "_api_meta")
        assert not hasattr(module, "register_schema")
        assert not hasattr(RestModule.on_load, "_task_type")
        assert not hasattr(RestModule.on_load, "_api_meta")
        source = inspect.getsource(RestModule)
        assert "register_schema" not in source
        assert "@task" not in source

    def test_uses_provider_call_not_communication(self) -> None:
        from rest import dispatcher as disp
        from rest import factory as fac

        dispatch_src = inspect.getsource(disp.RpcDispatcher.dispatch)
        assert "self._proxy.call" in dispatch_src
        blob = inspect.getsource(disp) + inspect.getsource(fac) + inspect.getsource(RestModule)
        assert "communication.api_proxy" not in blob
