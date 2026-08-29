"""REST Module — HTTP-транспорт к ApiProxyProvider.

Один маршрут: POST /api/v1/{module}/{function}. Тело JSON = kwargs.
Вызов только через ApiProxyProvider.call. Нет БД, нет @task.
"""
from __future__ import annotations

from typing import Any

from modules_system.module_base import ModuleBase, ModuleMeta

try:
    from .config import RestConfig
    from .factory import create_app
except ImportError:
    import importlib
    import sys
    from pathlib import Path as _Path

    _pkg_dir = _Path(__file__).resolve().parent
    _parent = "rest"

    def _lazy_import(module_name: str):
        full = f"{_parent}.{module_name}"
        if full not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                full, _pkg_dir / f"{module_name}.py",
            )
            mod = importlib.util.module_from_spec(spec)
            mod.__package__ = _parent
            sys.modules[full] = mod
            spec.loader.exec_module(mod)
        return sys.modules[full]

    RestConfig = _lazy_import("config").RestConfig  # type: ignore[assignment]
    create_app = _lazy_import("factory").create_app  # type: ignore[assignment]

__all__ = [
    "RestModule",
    "RestConfig",
    "create_app",
]

MODULE_VERSION = "1.0.0"


class RestModule(ModuleBase):
    """HTTP-вход в Mia. Транспорт, не домен."""

    @property
    def name(self) -> str:
        return "rest"

    @property
    def version(self) -> str:
        return MODULE_VERSION

    @property
    def meta(self) -> ModuleMeta:
        return ModuleMeta(dependencies=["log", "apiproxy"])

    def __init__(self, config: RestConfig | None = None) -> None:
        self._config = config or RestConfig.from_env()
        self._app: Any | None = None
        self._server: Any | None = None
        self._log = None

    def on_load(self, state: Any) -> None:
        self._log = state.log
        proxy = self._resolve_proxy(state)
        self._app = create_app(self._config, proxy, self._log)
        if self._config.bind:
            self._bind()
        self._log.info(
            "rest_module_loaded",
            extra={"version": self.version, "bind": self._config.bind},
        )

    def on_unload(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        self._app = None
        self._server = None
        if self._log is not None:
            self._log.info("rest_module_unloaded")
        self._log = None

    def _resolve_proxy(self, state: Any) -> Any | None:
        try:
            from modules.apiproxy.provider import ApiProxyProvider
            return state.services.resolve(ApiProxyProvider)
        except Exception:
            if self._log is not None:
                self._log.warning("ApiProxyProvider not found in DI")
            return None

    def _bind(self) -> None:
        import threading

        import uvicorn

        server = uvicorn.Server(
            uvicorn.Config(
                self._app,
                host=self._config.host,
                port=self._config.port,
                log_level="warning",
            ),
        )
        self._server = server
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
