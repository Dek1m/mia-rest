"""ASGI middleware: request_id, duration, лимит тела, логи, метрики."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from .envelope import EnvelopeFactory
from .metrics import rest_http_request_duration_seconds, rest_http_requests_total

__all__ = ["RestMiddleware", "path_labels"]


def path_labels(path: str) -> tuple[str, str]:
    """RPC → (module, function); системные → (_system, name)."""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "v1":
        return parts[2], parts[3]
    name = parts[-1] if parts else "unknown"
    if name == "openapi.json":
        name = "openapi"
    return "_system", name


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


def _content_length(scope: Scope) -> int | None:
    raw = _header(scope, b"content-length")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _args_keys(body: bytes) -> list[str]:
    if not body:
        return []
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return []
    if isinstance(parsed, dict):
        return list(parsed.keys())
    return []


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        chunks.append(message.get("body", b""))
        if not message.get("more_body"):
            break
    return b"".join(chunks)


class RestMiddleware:
    """request_id (echo), duration_ms, 413, access-логи без values/Authorization/Cookie."""

    def __init__(
        self,
        app: Any,
        *,
        max_body_bytes: int,
        envelope: EnvelopeFactory,
        log: Any | None = None,
    ) -> None:
        self._app = app
        self._max_body_bytes = max_body_bytes
        self._envelope = envelope
        self._log = log

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        await self._handle_http(scope, receive, send)

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        request_id = _header(scope, b"x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        path = str(scope.get("path", ""))
        method = str(scope.get("method", ""))
        module, function = path_labels(path)
        scope.setdefault("state", {})
        scope["state"]["request_id"] = request_id
        scope["state"]["started_perf"] = started

        length = _content_length(scope)
        if length is not None and length > self._max_body_bytes:
            await self._reject_too_large(
                scope, receive, send, request_id, started, method, path, module, function, [],
            )
            return

        body = await _read_body(receive)
        if len(body) > self._max_body_bytes:
            await self._reject_too_large(
                scope, receive, send, request_id, started, method, path, module, function, [],
            )
            return

        args_keys = _args_keys(body)
        self._log_event(
            "request_started", method, path, module, function, request_id, args_keys,
        )
        status_holder = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        consumed = {"done": False}

        async def receive_replay() -> Message:
            if consumed["done"]:
                return {"type": "http.request", "body": b"", "more_body": False}
            consumed["done"] = True
            return {"type": "http.request", "body": body, "more_body": False}

        try:
            await self._app(scope, receive_replay, send_wrapper)
        finally:
            self._finish(
                method, path, module, function, status_holder["code"],
                started, request_id, args_keys,
            )

    async def _reject_too_large(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        request_id: str,
        started: float,
        method: str,
        path: str,
        module: str,
        function: str,
        args_keys: list[str],
    ) -> None:
        duration_ms = int((time.perf_counter() - started) * 1000)
        payload = self._envelope.make(
            request_id=request_id,
            duration_ms=duration_ms,
            error=self._envelope.error_body("Payload too large", 413),
        )
        response = JSONResponse(
            status_code=413,
            content=payload,
            headers={"X-Request-Id": request_id},
        )
        self._log_event(
            "request_started", method, path, module, function, request_id, args_keys,
        )
        await response(scope, receive, send)
        self._finish(method, path, module, function, 413, started, request_id, args_keys)

    def _finish(
        self,
        method: str,
        path: str,
        module: str,
        function: str,
        status: int,
        started: float,
        request_id: str,
        args_keys: list[str],
    ) -> None:
        duration = time.perf_counter() - started
        status_label = str(status)
        rest_http_requests_total.labels(
            module=module, function=function, status=status_label,
        ).inc()
        rest_http_request_duration_seconds.labels(
            module=module, function=function, status=status_label,
        ).observe(duration)
        self._log_event(
            "request_completed",
            method, path, module, function, request_id, args_keys,
            status=status,
            duration_ms=int(duration * 1000),
        )

    def _log_event(
        self,
        event: str,
        method: str,
        path: str,
        module: str,
        function: str,
        request_id: str,
        args_keys: list[str],
        status: int | None = None,
        duration_ms: int | None = None,
    ) -> None:
        if self._log is None:
            return
        extra: dict[str, Any] = {
            "method": method,
            "path": path,
            "module": module,
            "function": function,
            "request_id": request_id,
            "args_keys": args_keys,
        }
        if status is not None:
            extra["status"] = status
        if duration_ms is not None:
            extra["duration_ms"] = duration_ms
        self._log.info(event, extra=extra)
