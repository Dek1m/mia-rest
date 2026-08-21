"""RPC-диспетчер: POST /api/v1/{module}/{function} → ApiProxyProvider.call."""
from __future__ import annotations

import json
import time
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from .cookie_auth import (
    COOKIE_CREDENTIAL_METHODS,
    access_cookie,
    apply_session_cookies,
    clear_session_cookies,
    has_albedo_cookie,
    is_spa_client,
    public_session_data,
    refresh_cookie,
)
from .envelope import EnvelopeFactory

__all__ = ["RpcDispatcher"]

_DEFAULT_SPA_ORIGINS = ("http://localhost:5173",)
_CLEAR_ON_CODES = frozenset({"REUSE_DETECTED", "AUTH_ERROR"})


def _sub_from_access(token: str | None) -> str | None:
    """sub из JWT без проверки подписи — authorize уже отсеет битый токен."""
    if not token:
        return None
    try:
        import jwt
        payload = jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


class RpcDispatcher:
    """Один маршрут. JSON-тело = kwargs. JWT не парсим."""

    def __init__(
        self,
        proxy: Any | None,
        envelope: EnvelopeFactory,
        log: Any | None = None,
        spa_origins: list[str] | None = None,
        cors_origins: list[str] | None = None,
    ) -> None:
        self._proxy = proxy
        self._envelope = envelope
        self._log = log
        self._spa_origins = list(spa_origins) if spa_origins else list(_DEFAULT_SPA_ORIGINS)
        self._cors_origins = list(cors_origins) if cors_origins else []

    async def dispatch(self, request: Request, module: str, function: str) -> JSONResponse:
        spa = is_spa_client(request)
        cookies = has_albedo_cookie(request)
        if cookies and not spa:
            return self.client_error(
                request, 403, "X-Albedo-Client: spa required", code="CSRF_HEADER",
            )
        if spa:
            origin_error = self._origin_mismatch(request)
            if origin_error is not None:
                return origin_error

        kwargs, error_response = await self._read_kwargs(request)
        if error_response is not None:
            return error_response
        token, kwargs = self._credentials(request, module, function, kwargs, spa)
        if self._proxy is None:
            return self.client_error(request, 503, "API proxy unavailable")
        result = await self._proxy.call(module, function, kwargs, token)
        return self._from_proxy(request, module, function, result, spa)

    def client_error(
        self,
        request: Request,
        status_code: int,
        message: str,
        code: str = "",
    ) -> JSONResponse:
        return self._json(
            request,
            status_code,
            data=None,
            error=self._envelope.error_body(message, status_code, code),
        )

    def _origin_mismatch(self, request: Request) -> JSONResponse | None:
        origin = request.headers.get("origin")
        if not origin:
            return None
        if origin in self._spa_origins:
            return None
        return self.client_error(
            request, 403, "Origin mismatch", code="ORIGIN_MISMATCH",
        )

    def _credentials(
        self,
        request: Request,
        module: str,
        function: str,
        kwargs: dict[str, Any],
        spa: bool,
    ) -> tuple[str | None, dict[str, Any]]:
        if spa:
            # Cookie побеждает: body refresh и Authorization игнорируем
            kwargs.pop("refresh_token", None)
            if (module, function) in COOKIE_CREDENTIAL_METHODS:
                refresh = refresh_cookie(request)
                if refresh is not None:
                    kwargs["refresh_token"] = refresh
            agent = request.headers.get("user-agent")
            if agent:
                kwargs["user_agent"] = agent
            client = request.client
            if client is not None and client.host:
                kwargs["ip"] = client.host
            token = access_cookie(request)
            session_id = _sub_from_access(token)
            if session_id:
                kwargs["_session_user_id"] = session_id
            return token, kwargs
        token = self._bearer_token(request)
        session_id = _sub_from_access(token)
        if session_id:
            kwargs["_session_user_id"] = session_id
        return token, kwargs

    def _bearer_token(self, request: Request) -> str | None:
        header = request.headers.get("authorization")
        if header is None:
            return None
        scheme, _, remainder = header.partition(" ")
        if scheme.lower() != "bearer" or not remainder.strip():
            return None
        return remainder.strip()

    async def _read_kwargs(self, request: Request) -> tuple[dict[str, Any] | None, JSONResponse | None]:
        raw = await request.body()
        if not raw.strip():
            # Пустое тело / нет Content-Type: kwargs={}, не 400
            return {}, None
        try:
            body = json.loads(raw)
        except Exception:
            return None, self.client_error(request, 400, "Invalid JSON")
        if not isinstance(body, dict):
            return None, self.client_error(request, 400, "JSON body must be an object")
        return body, None

    def _from_proxy(
        self,
        request: Request,
        module: str,
        function: str,
        result: dict[str, Any],
        spa: bool,
    ) -> JSONResponse:
        error = result.get("error")
        data = result.get("data")
        if error is None:
            status_code = 200
        else:
            status_code = int(error.get("status_code", 500))
            data = None
        if spa:
            data = self._spa_data(module, function, data)
        response = self._json(request, status_code, data=data, error=error)
        if spa:
            self._apply_cookies(response, module, function, result, status_code)
        return response

    def _spa_data(self, module: str, function: str, data: Any) -> Any:
        if module != "auth":
            return data
        if function in {"login", "refresh_token"}:
            return public_session_data(data)
        return data

    def _apply_cookies(
        self,
        response: JSONResponse,
        module: str,
        function: str,
        result: dict[str, Any],
        status_code: int,
    ) -> None:
        if module != "auth":
            return
        # Cookie-сессия + непустой CORS запрещены (ADR-001 §1)
        allow_set = not self._cors_origins
        error = result.get("error") or {}
        error_code = str(error.get("code", ""))
        if function == "logout" or (
            function == "refresh_token"
            and (status_code == 401 or error_code in _CLEAR_ON_CODES)
        ):
            clear_session_cookies(response)
            return
        if not allow_set:
            return
        raw = result.get("data")
        if function in {"login", "refresh_token"} and isinstance(raw, dict):
            access = raw.get("access_token")
            refresh = raw.get("refresh_token")
            if access and refresh:
                apply_session_cookies(response, str(access), str(refresh))

    def _json(
        self,
        request: Request,
        status_code: int,
        data: Any,
        error: dict[str, Any] | None,
    ) -> JSONResponse:
        request_id = str(getattr(request.state, "request_id", "") or "")
        started = float(getattr(request.state, "started_perf", time.perf_counter()))
        duration_ms = int((time.perf_counter() - started) * 1000)
        payload = self._envelope.make(
            request_id=request_id,
            duration_ms=duration_ms,
            data=data,
            error=error,
        )
        headers: dict[str, str] = {}
        if status_code == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(status_code=status_code, content=payload, headers=headers)
