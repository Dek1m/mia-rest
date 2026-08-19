"""Сервер — запуск uvicorn в фоне."""
from __future__ import annotations

import asyncio
import threading
from typing import Any

__all__ = ["run_server", "start_server_background"]


def run_server(app: Any, host: str = "0.0.0.0", port: int = 8000) -> None:
    """Запустить uvicorn (блокирующий вызов).

    Args:
        app: FastAPI приложение.
        host: Хост.
        port: Порт.
    """
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


def start_server_background(
    app: Any,
    host: str = "0.0.0.0",
    port: int = 8000,
    log: Any | None = None,
) -> threading.Thread:
    """Запустить uvicorn в фоновом потоке.

    Returns:
        Thread объект (daemon=True).
    """
    def _run() -> None:
        import uvicorn
        uvicorn.run(app, host=host, port=port, log_level="info")

    thread = threading.Thread(target=_run, daemon=True, name="mia-rest-server")
    thread.start()
    if log is not None:
        log.info("rest_server_started", host=host, port=port)
    return thread
