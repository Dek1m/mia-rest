"""Conftest для rest тестов — динамическая загрузка модуля rest."""
from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

_MODULE_DIR = Path(__file__).resolve().parent.parent

_fake_package = types.ModuleType("rest")
_fake_package.__path__ = [str(_MODULE_DIR)]  # type: ignore[attr-defined]
_fake_package.__package__ = "rest"
sys.modules["rest"] = _fake_package


def _load_submodule(name: str) -> types.ModuleType:
    file_path = _MODULE_DIR / f"{name}.py"
    if not file_path.exists():
        raise FileNotFoundError(f"Module file not found: {file_path}")
    full_name = f"rest.{name}"
    spec = importlib.util.spec_from_file_location(
        full_name, file_path, submodule_search_locations=[],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {full_name}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "rest"
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_load_submodule("config")
_load_submodule("envelope")
_load_submodule("metrics")
_load_submodule("cookie_auth")
_load_submodule("middleware")
_load_submodule("dispatcher")
_load_submodule("factory")

_init_spec = importlib.util.spec_from_file_location(
    "rest",
    _MODULE_DIR / "__init__.py",
    submodule_search_locations=[str(_MODULE_DIR)],
)
if _init_spec is None or _init_spec.loader is None:
    raise ImportError("Cannot load rest __init__.py")
_init_mod = importlib.util.module_from_spec(_init_spec)
_init_mod.__path__ = [str(_MODULE_DIR)]  # type: ignore[attr-defined]
_init_mod.__package__ = "rest"
sys.modules["rest"] = _init_mod
_init_spec.loader.exec_module(_init_mod)

from rest.config import RestConfig  # noqa: E402
from rest.factory import create_app  # noqa: E402


def _err(status_code: int, message: str) -> dict[str, Any]:
    return {
        "data": None,
        "error": {
            "code": f"ERROR_{status_code}",
            "message": message,
            "status_code": status_code,
        },
    }


def _ok(data: Any) -> dict[str, Any]:
    return {"data": data, "error": None}


class FakeApiProxyProvider:
    """Фейковый прокси: login, get_me, agents, boom. Без БД."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any], str | None]] = []

    async def call(
        self,
        module: str,
        method: str,
        kwargs: dict[str, Any],
        token: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append((module, method, kwargs, token))
        if module == "auth" and method == "login":
            return _ok({
                "access_token": "fake-token",
                "refresh_token": "fake-refresh",
                "user_id": "user-1",
                "username": "admin",
            })
        if module == "auth" and method == "refresh_token":
            if kwargs.get("refresh_token") == "reuse":
                return {
                    "data": None,
                    "error": {
                        "code": "REUSE_DETECTED",
                        "message": "Refresh token reuse detected",
                        "status_code": 401,
                    },
                }
            if not kwargs.get("refresh_token"):
                return _err(401, "Invalid or expired refresh token")
            return _ok({
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "user_id": "user-1",
                "username": "admin",
            })
        if module == "auth" and method == "logout":
            return _ok(True)
        if module == "auth" and method == "get_me":
            if not token:
                return _err(401, "Unauthorized")
            return _ok({"id": "user-1", "username": "admin"})
        if module == "auth" and method == "create_user":
            return _ok({"id": "new-user", "username": kwargs.get("username", "")})
        if module == "llm" and method == "agents":
            return _ok({
                "items": [{"id": "a1", "name": "agent"}],
                "page": kwargs.get("page", 1),
                "page_size": kwargs.get("page_size", 20),
                "total": 1,
            })
        if method == "boom":
            return _err(500, "boom")
        return _err(404, f"Method not found: {module}.{method}")

    def list_api(self, module_name: str | None = None) -> list[dict[str, Any]]:
        methods = [
            {
                "module": "auth",
                "name": "login",
                "description": "Вход в систему",
                "args": {"username": "str", "password": "str"},
                "return_type": "dict",
                "public": True,
                "required_permission": None,
            },
            {
                "module": "auth",
                "name": "get_me",
                "description": "Текущий пользователь",
                "args": {},
                "return_type": "dict",
                "public": False,
                "required_permission": "users:read",
            },
            {
                "module": "auth",
                "name": "create_user",
                "description": "Создать пользователя",
                "args": {"username": "str", "password": "str"},
                "return_type": "dict",
                "public": False,
                "required_permission": "users:create",
            },
            {
                "module": "llm",
                "name": "agents",
                "description": "Список агентов",
                "args": {"page": "int", "page_size": "int"},
                "return_type": "dict",
                "public": False,
                "required_permission": "agents:list",
            },
            {
                "module": "auth",
                "name": "boom",
                "description": "Внутренняя ошибка",
                "args": {},
                "return_type": "dict",
                "public": True,
                "required_permission": None,
            },
        ]
        if module_name:
            return [m for m in methods if m["module"] == module_name]
        return methods


class FakeLog:
    """Логгер, который копит записи. extra разворачивается как в Log."""

    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict[str, Any]]] = []

    def _store(self, level: str, message: str, kwargs: dict[str, Any]) -> None:
        extra = kwargs.pop("extra", None)
        payload = {**extra, **kwargs} if isinstance(extra, dict) else dict(kwargs)
        self.records.append((level, message, payload))

    def info(self, message: str, **kwargs: Any) -> None:
        self._store("info", message, kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._store("warning", message, kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._store("error", message, kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._store("debug", message, kwargs)


@pytest.fixture
def rest_config() -> RestConfig:
    return RestConfig(bind=False, docs=False, cors_origins=[], max_body_bytes=1_048_576)


@pytest.fixture
def fake_proxy() -> FakeApiProxyProvider:
    return FakeApiProxyProvider()


@pytest.fixture
def fake_log() -> FakeLog:
    return FakeLog()


@pytest.fixture
def app(rest_config: RestConfig, fake_proxy: FakeApiProxyProvider, fake_log: FakeLog):
    return create_app(rest_config, fake_proxy, fake_log)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
