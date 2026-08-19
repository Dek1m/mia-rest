"""FastAPI приложение — динамическая генерация маршрутов из MethodRegistry."""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.responses import Response

__all__ = ["create_app"]


def create_app(proxy_provider: Any | None = None, log: Any | None = None) -> Any:
    """Создать FastAPI приложение с маршрутами из реестра.

    Args:
        proxy_provider: ApiProxyProvider (опционально).

    Returns:
        FastAPI instance.
    """
    from fastapi import FastAPI, Request, Response
    from fastapi.responses import JSONResponse, RedirectResponse

    app = FastAPI(
        title="Mia REST API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Health check ────────────────────────────────────
    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    # ── Bootstrap эндпоинты ────────────────────────────
    _register_bootstrap_routes(app, proxy_provider)

    # ── Динамические маршруты из реестра ────────────────
    if proxy_provider is not None:
        _register_dynamic_routes(app, proxy_provider)

    return app


def _register_bootstrap_routes(app: Any, proxy_provider: Any | None) -> None:
    """Зарегистрировать bootstrap-эндпоинты."""
    from fastapi import Request
    from fastapi.responses import JSONResponse, RedirectResponse

    @app.get("/api/v1/auth/status")
    async def auth_status():
        """Публичный: проверить нужен ли bootstrap."""
        if proxy_provider is None:
            return JSONResponse(
                {"data": {"needs_bootstrap": True}, "error": None},
                status_code=200,
            )
        try:
            result = await proxy_provider.call(
                "auth", "needs_bootstrap", {},
            )
        except Exception as e:
            result = {"data": None, "error": {"code": "ERROR", "message": str(e), "status_code": 500}}
        return JSONResponse(result, status_code=200)

    @app.post("/api/v1/auth/bootstrap")
    async def auth_bootstrap(request: Request):
        """Публичный: создать первого администратора."""
        if proxy_provider is None:
            return JSONResponse(
                {"data": None, "error": {"code": "SERVICE_UNAVAILABLE", "message": "Proxy not available"}},
                status_code=503,
            )

        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                {"data": None, "error": {"code": "BAD_REQUEST", "message": "Invalid JSON body"}},
                status_code=400,
            )

        result = await proxy_provider.call(
            "auth", "bootstrap", body,
        )

        status = 200 if result.get("error") is None else (
            result["error"].get("status_code", 500)
        )

        # Проверяем 409 Conflict (bootstrap уже выполнен)
        if result.get("error") and "already" in result["error"].get("message", "").lower():
            status = 409

        return JSONResponse(result, status_code=status)


def _register_dynamic_routes(app: Any, proxy_provider: Any) -> None:
    """Зарегистрировать динамические маршруты из MethodRegistry.

    Генерирует:
    - POST /api/v1/{module}/{method} — JSON body
    - GET /api/v1/{module}?method={method}&... — query params
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse, RedirectResponse

    registry = proxy_provider.registry

    for module_meta in registry.list_all_methods():
        module_name = module_meta.module

        # POST маршрут для каждого метода
        _register_post_route(app, proxy_provider, module_name, module_meta.name)

        # GET маршрут для модуля (с query params)
        _register_get_route(app, proxy_provider, module_name)

    # GET /api/v1 — список всех модулей и методов
    @app.get("/api/v1")
    async def list_modules():
        result = proxy_provider.list_api()
        # list_api() decorated with @task returns TaskFuture
        if hasattr(result, "result"):
            result = result.result()
        modules = {}
        for m in result:
            mod = m["module"]
            if mod not in modules:
                modules[mod] = []
            modules[mod].append({
                "name": m["name"],
                "description": m["description"],
                "args": m["args"],
                "public": m["public"],
            })
        return {"data": modules, "error": None}


def _register_post_route(
    app: Any,
    proxy_provider: Any,
    module_name: str,
    method_name: str,
) -> None:
    """Зарегистрировать POST /api/v1/{module}/{method}."""

    async def handler(request: Request) -> Response:
        # Извлекаем токен
        token = _extract_token(request)

        # Получаем тело запроса
        try:
            body = await request.json()
        except Exception:
            body = {}

        # Вызов через proxy
        try:
            result = await proxy_provider.call(
                module_name, method_name, body, token=token,
            )
        except Exception as e:
            result = {"data": None, "error": {"code": "ERROR_500", "message": str(e), "status_code": 500}}

        # Определяем статус-код
        status = _result_to_status(result)

        # Браузерный редирект на 401
        if status == 401 and _is_browser_request(request):
            return RedirectResponse(url="/auth/login", status_code=302)

        return JSONResponse(result, status_code=status)

    # Устанавливаем имя функции для OpenAPI
    handler.__name__ = f"{module_name}_{method_name}"
    handler.__qualname__ = f"{module_name}_{method_name}"

    app.add_api_route(
        f"/api/v1/{module_name}/{method_name}",
        handler,
        methods=["POST"],
        tags=[module_name],
    )


def _register_get_route(
    app: Any,
    proxy_provider: Any,
    module_name: str,
) -> None:
    """Зарегистрировать GET /api/v1/{module}?method={method}&... для публичных методов."""

    async def handler(request: Request) -> Response:
        # Извлекаем токен
        token = _extract_token(request)

        # Query params
        params = dict(request.query_params)
        method_name = params.pop("method", None)

        if not method_name:
            return JSONResponse(
                {"data": None, "error": {"code": "BAD_REQUEST", "message": "Missing 'method' query parameter"}},
                status_code=400,
            )

        # Конвертируем строки в типы (int/float/bool)
        kwargs = {}
        for k, v in params.items():
            kwargs[k] = _coerce_query_value(v)

        result = await proxy_provider.call(
            module_name, method_name, kwargs, token=token,
        )

        status = _result_to_status(result)

        # Браузерный редирект на 401
        if status == 401 and _is_browser_request(request):
            return RedirectResponse(url="/auth/login", status_code=302)

        return JSONResponse(result, status_code=status)

    handler.__name__ = f"{module_name}_get"
    handler.__qualname__ = f"{module_name}_get"

    app.add_api_route(
        f"/api/v1/{module_name}",
        handler,
        methods=["GET"],
        tags=[module_name],
    )


def _extract_token(request: Any) -> str | None:
    """Извлечь Bearer token из заголовка Authorization."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _result_to_status(result: dict[str, Any]) -> int:
    """Определить HTTP статус-код из результата proxy.call()."""
    if result.get("error"):
        code = result["error"].get("status_code", 500)
        return code
    return 200


def _is_browser_request(request: Any) -> bool:
    """Проверить, является ли запрос из браузера."""
    accept = request.headers.get("accept", "")
    return "text/html" in accept


def _coerce_query_value(value: str) -> Any:
    """Привести строковое значение query-параметра к типу."""
    # Bool
    if value.lower() in ("true", "1"):
        return True
    if value.lower() in ("false", "0"):
        return False
    # Int
    try:
        return int(value)
    except ValueError:
        pass
    # Float
    try:
        return float(value)
    except ValueError:
        pass
    return value
