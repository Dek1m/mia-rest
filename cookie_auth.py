"""Сборка HttpOnly cookies сессии albedo. Без Domain — префикс __Host-."""
from __future__ import annotations

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
    value = request.cookies.get(ACCESS_COOKIE)
    return value or None


def refresh_cookie(request: Request) -> str | None:
    value = request.cookies.get(REFRESH_COOKIE)
    return value or None


def has_albedo_cookie(request: Request) -> bool:
    return access_cookie(request) is not None or refresh_cookie(request) is not None


def apply_session_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    _write_cookie(response, ACCESS_COOKIE, access_token, ACCESS_MAX_AGE, "lax")
    _write_cookie(response, REFRESH_COOKIE, refresh_token, REFRESH_MAX_AGE, "strict")


def clear_session_cookies(response: Response) -> None:
    # Twin-атрибуты обязательны, иначе браузер не сотрёт __Host-
    _write_cookie(response, ACCESS_COOKIE, "", 0, "lax")
    _write_cookie(response, REFRESH_COOKIE, "", 0, "strict")


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
        secure=True,
        httponly=True,
        samesite=samesite,
    )
