"""RPC-диспетчер: POST /api/v1/{module}/{function} → ApiProxyProvider.call."""
from __future__ import annotations

import json
import time
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from .envelope import EnvelopeFactory

__all__ = ["RpcDispatcher"]


class RpcDispatcher:
    """Один маршрут. JSON-тело = kwargs. JWT не парсим."""

    def __init__(
        self,
        proxy: Any | None,
        envelope: EnvelopeFactory,
        log: Any | None = None,
    ) -> None:
        self._proxy = proxy
        self._envelope = envelope
        self._log = log

    async def dispatch(self, request: Request, module: str, function: str) -> JSONResponse:
        token = self._bearer_token(request)
        kwargs, error_response = await self._read_kwargs(request)
        if error_response is not None:
            return error_response
        if self._proxy is None:
            return self.client_error(request, 503, "API proxy unavailable")
        result = await self._proxy.call(module, function, kwargs, token)
        return self._from_proxy(request, result)

    def client_error(self, request: Request, status_code: int, message: str) -> JSONResponse:
        return self._json(
            request,
            status_code,
            data=None,
            error=self._envelope.error_body(message, status_code),
        )

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

    def _from_proxy(self, request: Request, result: dict[str, Any]) -> JSONResponse:
        error = result.get("error")
        data = result.get("data")
        if error is None:
            return self._json(request, 200, data=data, error=None)
        status_code = int(error.get("status_code", 500))
        return self._json(request, status_code, data=None, error=error)

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
