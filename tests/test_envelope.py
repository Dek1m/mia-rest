"""Tests for EnvelopeFactory."""
from __future__ import annotations

from rest.envelope import EnvelopeFactory


def test_success_shape() -> None:
    body = EnvelopeFactory().make(
        request_id="rid-1",
        duration_ms=7,
        data={"ok": True},
        error=None,
    )
    assert set(body) == {"data", "error", "meta"}
    assert body["data"] == {"ok": True}
    assert body["error"] is None
    assert body["meta"] == {
        "request_id": "rid-1",
        "duration_ms": 7,
        "client_type": "rest",
    }


def test_error_shape() -> None:
    factory = EnvelopeFactory()
    error = factory.error_body("nope", 401)
    body = factory.make(request_id="rid-2", duration_ms=1, error=error)
    assert body["data"] is None
    assert body["error"]["status_code"] == 401
    assert body["error"]["code"] == "ERROR_401"
    assert body["meta"]["client_type"] == "rest"


def test_client_type_is_hardcoded() -> None:
    body = EnvelopeFactory().make(request_id="x", duration_ms=0, data={})
    assert body["meta"]["client_type"] == "rest"
