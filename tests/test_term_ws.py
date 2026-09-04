"""WebSocket PTY: без cookie — 4401."""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect


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
