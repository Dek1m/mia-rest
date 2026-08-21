"""Сборка HttpOnly cookies сессии albedo.

HTTPS / MIA_REST_COOKIE_SECURE=true (дефолт): __Host-albedo_* + Secure.
HTTP-тест / MIA_REST_COOKIE_SECURE=false: albedo_* без Secure (__Host- на HTTP не встанет).
"""
from __future__ import annotations

import os
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

__all__ = [
    "ACCESS_COOKIE",
    "REFRESH_COOKIE",
    "SPA_HEADER",
    "SPA_VALUE",
    "ACCESS_MAX_AGE",
    "REFRESH_MAX_AGE",
    "apply_session_cookies",
    "clear_session_cookies",
    "access_cookie",
    "refresh_cookie",
    "has_albedo_cookie",
    "is_spa_client",
    "public_session_data",
    "COOKIE_CREDENTIAL_METHODS",
]

ACCESS_COOKIE = "__Host-albedo_at"
REFRESH_COOKIE = "__Host-albedo_rt"
ACCESS_COOKIE_INSECURE = "albedo_at"
REFRESH_COOKIE_INSECURE = "albedo_rt"
_TRUE = {"1", "true", "yes", "on"}


def cookies_secure() -> bool:
    raw = os.getenv("MIA_REST_COOKIE_SECURE", "true")
    return raw.strip().lower() in _TRUE


def access_cookie_name() -> str:
    return ACCESS_COOKIE if cookies_secure() else ACCESS_COOKIE_INSECURE


def refresh_cookie_name() -> str:
    return REFRESH_COOKIE if cookies_secure() else REFRESH_COOKIE_INSECURE
SPA_HEADER = "x-albedo-client"
SPA_VALUE = "spa"
ACCESS_MAX_AGE = 900
REFRESH_MAX_AGE = 2_592_000

# refresh/logout: credential = cookie, живой access JWT не нужен
COOKIE_CREDENTIAL_METHODS = frozenset({
    ("auth", "refresh_token"),
    ("auth", "logout"),
})

_TOKEN_KEYS = frozenset({"access_token", "refresh_token"})


def is_spa_client(request: Request) -> bool:
    return request.headers.get(SPA_HEADER, "").strip().lower() == SPA_VALUE


def access_cookie(request: Request) -> str | None:
    return (
        request.cookies.get(access_cookie_name())
        or request.cookies.get(ACCESS_COOKIE)
        or request.cookies.get(ACCESS_COOKIE_INSECURE)
        or None
    )


def refresh_cookie(request: Request) -> str | None:
    return (
        request.cookies.get(refresh_cookie_name())
        or request.cookies.get(REFRESH_COOKIE)
        or request.cookies.get(REFRESH_COOKIE_INSECURE)
        or None
    )


def has_albedo_cookie(request: Request) -> bool:
    return access_cookie(request) is not None or refresh_cookie(request) is not None


def apply_session_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    _write_cookie(response, access_cookie_name(), access_token, ACCESS_MAX_AGE, "lax")
    _write_cookie(response, refresh_cookie_name(), refresh_token, REFRESH_MAX_AGE, "strict")


def clear_session_cookies(response: Response) -> None:
    # Twin-атрибуты обязательны, иначе браузер не сотрёт cookie
    for name, site in (
        (access_cookie_name(), "lax"),
        (refresh_cookie_name(), "strict"),
        (ACCESS_COOKIE, "lax"),
        (REFRESH_COOKIE, "strict"),
        (ACCESS_COOKIE_INSECURE, "lax"),
        (REFRESH_COOKIE_INSECURE, "strict"),
    ):
        _write_cookie(response, name, "", 0, site)


def public_session_data(data: Any) -> Any:
    """Убрать токены из JSON для SPA."""
    if not isinstance(data, dict):
        return data
    return {key: value for key, value in data.items() if key not in _TOKEN_KEYS}


def _write_cookie(
    response: Response,
    name: str,
    value: str,
    max_age: int,
    samesite: str,
) -> None:
    # Domain не передаём: __Host- запрещает атрибут
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        path="/",
        secure=cookies_secure(),
        httponly=True,
        samesite=samesite,
    )
