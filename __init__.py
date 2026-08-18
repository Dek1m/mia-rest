"""REST Module — HTTP API на FastAPI для Mia Framework.

Генерирует маршруты из MethodRegistry (динамические).
Поддерживает два стиля: POST /api/v1/{module}/{method} и GET /api/v1/{module}?method=...
"""
from __future__ import annotations

import importlib
import sys
from typing import Any

# Lazy imports — работают и через exec(), и через нормальный import
def _lazy_import(module_name: str):
    """Ленивый импорт подмодуля."""
    full_name = f"rest.{module_name}"
    if full_name not in sys.modules:
        spec = importlib.util.find_spec(full_name)
        if spec is None:
            # Fallback: загружаем напрямую
            from pathlib import Path
            pkg_dir = Path(__file__).parent
            file_path = pkg_dir / f"{module_name}.py"
            if file_path.exists():
                spec = importlib.util.spec_from_file_location(full_name, file_path)
            else:
                raise ImportError(f"Cannot find {module_name}")
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "rest"
        sys.modules[full_name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[full_name]


def _get_class(module_name: str, class_name: str) -> Any:
    """Получить класс из подмодуля."""
    mod = _lazy_import(module_name)
    return getattr(mod, class_name)


# Ленивые свойства для основных классов
def __getattr__(name: str) -> Any:
    if name == "RestConfig":
        return _get_class("config", "RestConfig")
    if name == "create_app":
        return _get_class("app", "create_app")
    if name == "RestModule":
        # Импортируем ModuleBase только если доступен
        try:
            from modules_system.module_base import ModuleBase
        except ImportError:
            class ModuleBase:
                pass

        config_mod = _lazy_import("config")
        app_mod = _lazy_import("app")

        class RestModule(ModuleBase):
            @property
            def name(self):
                return "rest"

            @property
            def version(self):
                return MODULE_VERSION

            @property
            def meta(self):
                from modules_system.module_base import ModuleMeta
                return ModuleMeta(
                    dependencies=["apiproxy"],
                )

            def __init__(self, config=None):
                self._config = config or config_mod.RestConfig.from_env()
                self._app = None

            def on_load(self, state):
                proxy_provider = None
                try:
                    from modules.apiproxy.provider import ApiProxyProvider
                    proxy_provider = state.services.resolve(ApiProxyProvider)
                except Exception:
                    pass
                self._app = app_mod.create_app(proxy_provider=proxy_provider)

            def on_unload(self):
                self._app = None

        return RestModule
    raise AttributeError(f"module 'rest' has no attribute {name}")


__all__ = ["RestModule", "RestConfig", "create_app"]

MODULE_VERSION = "1.0.0"
