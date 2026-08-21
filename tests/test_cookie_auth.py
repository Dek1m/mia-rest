"""Атрибуты __Host- cookies: Path=/, Secure, без Domain, twin Max-Age=0."""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from rest.cookie_auth import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    apply_session_cookies,
    clear_session_cookies,
    has_albedo_cookie,
    is_spa_client,
    public_session_data,
)


def test_apply_session_cookies_host_prefix() -> None:
    response = Response()
    apply_session_cookies(response, "at", "rt")
    cookies = response.headers.getlist("set-cookie")
    blob = "\n".join(cookies)
    assert ACCESS_COOKIE in blob
    assert REFRESH_COOKIE in blob
    assert "Domain=" not in blob
    assert "Path=/" in blob
    assert "Secure" in blob
    assert "HttpOnly" in blob


def test_clear_session_cookies_twin() -> None:
    response = Response()
    clear_session_cookies(response)
    cookies = response.headers.getlist("set-cookie")
    assert len(cookies) == 2
    blob = "\n".join(cookies)
    assert "Max-Age=0" in blob
    assert ACCESS_COOKIE in blob
    assert REFRESH_COOKIE in blob
    assert "Domain=" not in blob


def test_public_session_data_strips_tokens() -> None:
    assert public_session_data({
        "access_token": "a",
        "refresh_token": "r",
        "user_id": "u",
        "username": "n",
    }) == {"user_id": "u", "username": "n"}


def test_is_spa_and_cookie_presence() -> None:
    scope = {
        "type": "http",
        "headers": [
            (b"x-albedo-client", b"spa"),
            (b"cookie", b"__Host-albedo_at=x"),
        ],
    }
    request = Request(scope)
    assert is_spa_client(request)
    assert has_albedo_cookie(request)
