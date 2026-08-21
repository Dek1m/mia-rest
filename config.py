"""REST Module Configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

__all__ = ["RestConfig"]

_TRUE = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class RestConfig:
    """Конфигурация rest-модуля. Приоритет: аргументы > ENV > дефолты."""

    host: str = "127.0.0.1"
    port: int = 8080
    bind: bool = True
    cors_origins: list[str] = field(default_factory=list)
    max_body_bytes: int = 1_048_576
    docs: bool = False

    @classmethod
    def from_env(cls) -> RestConfig:
        """Прочитать MIA_REST_* из окружения."""
        return cls(
            host=os.getenv("MIA_REST_HOST", "127.0.0.1"),
            port=_env_int("MIA_REST_PORT", 8080),
            bind=_env_bool("MIA_REST_BIND", True),
            cors_origins=_env_list("MIA_REST_CORS_ORIGINS"),
            max_body_bytes=_env_int("MIA_REST_MAX_BODY_BYTES", 1_048_576),
            docs=_env_bool("MIA_REST_DOCS", False),
        )
