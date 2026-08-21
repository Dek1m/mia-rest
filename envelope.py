"""Envelope REST-ответа: {data, error, meta}."""
from __future__ import annotations

from typing import Any

__all__ = ["EnvelopeFactory"]

_CLIENT_TYPE = "rest"


class EnvelopeFactory:
    """Сборка канонического envelope. client_type всегда rest."""

    def make(
        self,
        *,
        request_id: str,
        duration_ms: int,
        data: Any = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "data": data,
            "error": error,
            "meta": {
                "request_id": request_id,
                "duration_ms": duration_ms,
                "client_type": _CLIENT_TYPE,
            },
        }

    def error_body(self, message: str, status_code: int, code: str = "") -> dict[str, Any]:
        return {
            "code": code or f"ERROR_{status_code}",
            "message": message,
            "status_code": status_code,
        }
