"""Сборка FastAPI-приложения rest."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response

from .config import RestConfig
from .cookie_auth import access_cookie
from .dispatcher import RpcDispatcher
from .envelope import EnvelopeFactory
from .middleware import RestMiddleware

__all__ = ["create_app", "build_openapi"]

_TYPE_MAP = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}


def create_app(config: RestConfig, proxy: Any | None, log: Any | None) -> FastAPI:
    """HTTP-приложение. docs_url/redoc/openapi автоген отключены."""
    envelope = EnvelopeFactory()
    dispatcher = RpcDispatcher(
        proxy=proxy,
        envelope=envelope,
        log=log,
        spa_origins=config.spa_origins,
        cors_origins=config.cors_origins,
    )
    app = FastAPI(title="Mia REST", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.proxy = proxy
    app.state.log = log
    app.state.envelope = envelope
    app.state.dispatcher = dispatcher
    _mount_middleware(app, config, envelope, log)
    _mount_routes(app, config, proxy, dispatcher)
    _mount_handlers(app, dispatcher)
    return app


def _mount_middleware(
    app: FastAPI,
    config: RestConfig,
    envelope: EnvelopeFactory,
    log: Any | None,
) -> None:
    app.add_middleware(
        RestMiddleware,
        max_body_bytes=config.max_body_bytes,
        envelope=envelope,
        log=log,
    )
    # Cookie-сессия + непустой CORS запрещены (ADR-001). Дефолт — пустой список.
    if config.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


def _mount_routes(
    app: FastAPI,
    config: RestConfig,
    proxy: Any | None,
    dispatcher: RpcDispatcher,
) -> None:
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request) -> JSONResponse:
        if proxy is None:
            return dispatcher.client_error(request, 503, "API proxy unavailable")
        return JSONResponse({"status": "ok"})

    @app.get("/openapi.json")
    async def openapi_spec(request: Request) -> JSONResponse:
        if not config.docs:
            return dispatcher.client_error(request, 404, "OpenAPI disabled")
        methods = proxy.list_api() if proxy is not None else []
        return JSONResponse(build_openapi(methods))

    @app.get("/api/v1/auth/avatar")
    async def avatar(request: Request) -> Response:
        # GET байтов для <img>. Без SPA-header ок. CSRF не применяется.
        return await _serve_avatar(request, proxy, dispatcher)

    @app.post("/api/v1/{module}/{function}")
    async def rpc(module: str, function: str, request: Request) -> JSONResponse:
        return await dispatcher.dispatch(request, module, function)


def _mount_handlers(app: FastAPI, dispatcher: RpcDispatcher) -> None:
    @app.exception_handler(RequestValidationError)
    async def on_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return dispatcher.client_error(request, 400, "Invalid request")


async def _serve_avatar(
    request: Request,
    proxy: Any | None,
    dispatcher: RpcDispatcher,
) -> Response:
    if proxy is None:
        return dispatcher.client_error(request, 503, "API proxy unavailable")
    auth = getattr(proxy, "auth_provider", None)
    if auth is None:
        return dispatcher.client_error(request, 401, "Authentication required")
    token = access_cookie(request)
    if not token:
        return dispatcher.client_error(request, 401, "Authentication required")
    ctx = await auth.validate_token(token)
    if ctx is None:
        return dispatcher.client_error(request, 401, "Invalid or expired token")
    payload = await auth.get_avatar_bytes(ctx.user_id)
    if payload is None:
        return dispatcher.client_error(request, 404, "Avatar not found")
    raw, content_type = payload
    return Response(
        content=raw,
        media_type=content_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def build_openapi(methods: list[dict[str, Any]]) -> dict[str, Any]:
    """OpenAPI 3 из proxy.list_api(). Не автоген FastAPI catch-all."""
    paths: dict[str, Any] = {}
    for meta in methods:
        module = str(meta.get("module", ""))
        name = str(meta.get("name", ""))
        if not module or not name:
            continue
        paths[f"/api/v1/{module}/{name}"] = {"post": _operation(meta)}
    return {
        "openapi": "3.0.3",
        "info": {"title": "Mia REST API", "version": "1.0.0"},
        "paths": paths,
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
            },
        },
    }


def _operation(meta: dict[str, Any]) -> dict[str, Any]:
    args = meta.get("args") or {}
    properties = {
        key: {"type": _TYPE_MAP.get(str(typ), "string")}
        for key, typ in args.items()
    }
    operation: dict[str, Any] = {
        "operationId": f"{meta.get('module')}_{meta.get('name')}",
        "summary": meta.get("description") or "",
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"type": "object", "properties": properties},
                },
            },
        },
        "responses": {"200": {"description": "OK"}},
    }
    if not meta.get("public"):
        operation["security"] = [{"bearerAuth": []}]
    return operation
