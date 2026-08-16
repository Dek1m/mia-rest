"""REST Module Configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["RestConfig"]


@dataclass
class RestConfig:
    """Конфигурация REST-модуля.

    Приоритет: прямые аргументы > ENV > дефолты.
    """

    host: str = "0.0.0.0"
    port: int = 8000
    enabled: bool = True

    @classmethod
    def from_env(cls) -> RestConfig:
        return cls(
            host=os.getenv("MIA_REST_HOST", "0.0.0.0"),
            port=int(os.getenv("MIA_REST_PORT", "8000")),
            enabled=os.getenv("MIA_REST_ENABLED", "true").lower() == "true",
        )
