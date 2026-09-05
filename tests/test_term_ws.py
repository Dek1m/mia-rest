"""WebSocket PTY: без cookie — 4401, без term:access — 4403."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from rest.factory import create_app


def test_pty_requires_cookie(client) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/term/pty?session_id=s1") as ws:
            ws.receive_text()
    assert exc.value.code == 4401


def test_pty_requires_session(client) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/term/pty") as ws:
            ws.receive_text()
    assert exc.value.code == 4400


def _pty_app(rest_config, fake_log, *, allowed: bool, with_term: bool):
    checked: list[tuple[str, str]] = []

    class _Auth:
        async def validate_token(self, token: str):
            return {"user_id": "u1", "username": "ada"} if token == "tok" else None

        async def check_permission(self, user_id: str, permission: str) -> bool:
            checked.append((user_id, permission))
            return allowed

    class _Proxy:
        auth_provider = _Auth()
        term_provider = object() if with_term else None

    return create_app(rest_config, _Proxy(), fake_log), checked


def test_pty_denied_without_term_access(rest_config, fake_log) -> None:
    app, checked = _pty_app(rest_config, fake_log, allowed=False, with_term=True)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                "/api/v1/term/pty?session_id=s1",
                cookies={"__Host-albedo_at": "tok"},
            ) as ws:
                ws.receive_text()
    assert exc.value.code == 4403
    assert checked == [("u1", "term:access")]


def test_pty_permission_granted_proceeds(rest_config, fake_log) -> None:
    # term_provider=None → после успешной проверки прав 4404 (нет провайдера)
    app, checked = _pty_app(rest_config, fake_log, allowed=True, with_term=False)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(
                "/api/v1/term/pty?session_id=s1",
                cookies={"__Host-albedo_at": "tok"},
            ) as ws:
                ws.receive_text()
    assert exc.value.code == 4404
    assert checked == [("u1", "term:access")]
