"""WebSocket PTY для term. Cookie-сессия, без SPA-заголовка."""
from __future__ import annotations

from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from .cookie_auth import ACCESS_COOKIE, ACCESS_COOKIE_INSECURE, access_cookie_name

__all__ = ["term_pty"]


def _token(websocket: WebSocket) -> str | None:
    return (
        websocket.cookies.get(access_cookie_name())
        or websocket.cookies.get(ACCESS_COOKIE)
        or websocket.cookies.get(ACCESS_COOKIE_INSECURE)
        or None
    )


def _ctx_user_id(ctx: Any) -> str | None:
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        value = ctx.get("user_id")
        return str(value) if value else None
    value = getattr(ctx, "user_id", None)
    return str(value) if value else None


def _ctx_username(ctx: Any) -> str | None:
    if ctx is None:
        return None
    if isinstance(ctx, dict):
        value = ctx.get("username")
        return str(value) if value else None
    value = getattr(ctx, "username", None)
    return str(value) if value else None


async def _close(websocket: WebSocket, code: int) -> None:
    if websocket.client_state == WebSocketState.CONNECTED:
        await websocket.close(code=code)


async def term_pty(websocket: WebSocket, proxy: Any | None) -> None:
    session_id = (websocket.query_params.get("session_id") or "").strip()
    await websocket.accept()
    if not session_id:
        await _close(websocket, 4400)
        return
    token = _token(websocket)
    if not token:
        await _close(websocket, 4401)
        return
    auth = getattr(proxy, "auth_provider", None) if proxy is not None else None
    if auth is None:
        await _close(websocket, 4503)
        return
    try:
        ctx = await auth.validate_token(token)
    except Exception:
        await _close(websocket, 4401)
        return
    user_id = _ctx_user_id(ctx)
    if not user_id:
        await _close(websocket, 4401)
        return
    term = getattr(proxy, "term_provider", None) if proxy is not None else None
    if callable(term) and not hasattr(term, "attach_pty"):
        term = term()
    if term is None or not hasattr(term, "attach_pty"):
        await _close(websocket, 4404)
        return
    try:
        await term.attach_pty(websocket, session_id, user_id, _ctx_username(ctx))
    except WebSocketDisconnect:
        return
    except Exception as exc:
        code = getattr(exc, "code", "")
        if code == "NOT_FOUND":
            await _close(websocket, 4404)
        elif code == "FORBIDDEN":
            await _close(websocket, 4403)
        else:
            await _close(websocket, 1011)
