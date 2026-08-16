"""Tests for REST Module — фикстуры и моки."""
from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

# ── Динамическая загрузка rest ──────────────────────

_MODULE_DIR = Path(__file__).resolve().parent.parent

_fake_package = types.ModuleType("rest")
_fake_package.__path__ = [str(_MODULE_DIR)]  # type: ignore[attr-defined]
_fake_package.__package__ = "rest"
sys.modules["rest"] = _fake_package


def _load_submodule(name: str) -> types.ModuleType:
    file_path = _MODULE_DIR / f"{name}.py"
    full_name = f"rest.{name}"
    spec = importlib.util.spec_from_file_location(full_name, file_path, submodule_search_locations=[])
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {full_name}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "rest"
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_config = _load_submodule("config")
_app = _load_submodule("app")
_server = _load_submodule("server")

from rest.config import RestConfig  # noqa: E402
from rest.app import create_app  # noqa: E402
from rest.server import run_server, start_server_background  # noqa: E402

# ── Загрузка apiproxy ─────────────────────────────

_APIPROXY_DIR = Path(__file__).resolve().parent.parent.parent / "apiproxy"
_fake_apiproxy = types.ModuleType("apiproxy")
_fake_apiproxy.__path__ = [str(_APIPROXY_DIR)]  # type: ignore[attr-defined]
_fake_apiproxy.__package__ = "apiproxy"
sys.modules["apiproxy"] = _fake_apiproxy


def _load_apiproxy_submodule(name: str) -> types.ModuleType:
    file_path = _APIPROXY_DIR / f"{name}.py"
    full_name = f"apiproxy.{name}"
    spec = importlib.util.spec_from_file_location(full_name, file_path, submodule_search_locations=[])
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {full_name}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "apiproxy"
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_load_apiproxy_submodule("config")
_load_apiproxy_submodule("registry")
_load_apiproxy_submodule("middleware")
_load_apiproxy_submodule("converter")
_load_apiproxy_submodule("provider")

from apiproxy.registry import MethodRegistry, MethodMeta  # noqa: E402
from apiproxy.provider import ApiProxyProvider  # noqa: E402
from apiproxy.config import ApiproxyConfig  # noqa: E402

# ── Загрузка auth decorators ───────────────────────────

_AUTH_DIR = Path(__file__).resolve().parent.parent.parent / "auth"
_fake_auth = types.ModuleType("auth")
_fake_auth.__path__ = [str(_AUTH_DIR)]  # type: ignore[attr-defined]
_fake_auth.__package__ = "auth"
sys.modules["auth"] = _fake_auth


def _load_auth_submodule(name: str) -> types.ModuleType:
    file_path = _AUTH_DIR / f"{name}.py"
    full_name = f"auth.{name}"
    spec = importlib.util.spec_from_file_location(full_name, file_path, submodule_search_locations=[])
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create spec for {full_name}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "auth"
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


_load_auth_submodule("decorators")

from auth.decorators import auth_method  # noqa: E402


# ── Фейковый proxy provider ────────────────────────────

class FakeProvider:
    """Фейковый провайдер с методами для тестирования."""

    @auth_method(
        name="login",
        description="Вход в систему",
        args={"username": "str", "password": "str"},
        return_type="dict",
        public=True,
    )
    async def login(self, username: str = "", password: str = "") -> dict[str, Any]:
        return {"access_token": "fake-token", "user_id": "user-1"}

    @auth_method(
        name="get_me",
        description="Получить данные текущего пользователя",
        args={},
        return_type="dict",
        public=False,
        required_permission="users:read",
    )
    async def get_me(self) -> dict[str, Any]:
        return {"id": "user-1", "username": "admin"}

    @auth_method(
        name="list_users",
        description="Список пользователей",
        args={"limit": "int", "offset": "int"},
        return_type="dict",
        public=False,
        required_permission="users:list",
    )
    async def list_users(self, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        return {"items": [{"id": "1", "name": "Admin"}], "total": 1, "offset": offset, "limit": limit}

    @auth_method(
        name="status",
        description="Статус bootstrap",
        args={},
        return_type="bool",
        public=True,
    )
    async def needs_bootstrap(self) -> bool:
        return True

    @auth_method(
        name="bootstrap",
        description="Bootstrap: создать первого администратора",
        args={"username": "str", "password": "str"},
        return_type="dict",
        public=True,
    )
    async def bootstrap(self, username: str = "", password: str = "", email: str = "") -> dict[str, Any]:
        return {"access_token": "bootstrap-token", "user_id": "admin-1"}


@pytest.fixture
def fake_registry() -> MethodRegistry:
    """Фейковый реестр с тестовыми методами."""
    registry = MethodRegistry()
    provider = FakeProvider()
    registry.collect_from_module(provider, "auth")
    return registry


@pytest.fixture
def fake_proxy_provider(fake_registry: MethodRegistry) -> ApiProxyProvider:
    """Фейковый ApiProxyProvider с test-методами."""
    config = ApiproxyConfig(whitelist=["auth"])
    proxy = ApiProxyProvider(config=config)
    proxy._registry = fake_registry
    return proxy


@pytest.fixture
def app(fake_proxy_provider):
    """FastAPI app с фейковым proxy."""
    return create_app(proxy_provider=fake_proxy_provider)
