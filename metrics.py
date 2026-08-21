"""HTTP-метрики rest. Не путать с api_calls_total ядра."""
from __future__ import annotations

from prometheus_client import REGISTRY, Counter, Histogram

__all__ = ["rest_http_requests_total", "rest_http_request_duration_seconds"]


def _counter(name: str, documentation: str, labelnames: list[str]) -> Counter:
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Counter(name, documentation, labelnames)


def _histogram(name: str, documentation: str, labelnames: list[str]) -> Histogram:
    existing = REGISTRY._names_to_collectors.get(name)
    if existing is not None:
        return existing  # type: ignore[return-value]
    return Histogram(
        name,
        documentation,
        labelnames,
        buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    )


rest_http_requests_total = _counter(
    "rest_http_requests_total",
    "Total REST HTTP requests",
    ["module", "function", "status"],
)

rest_http_request_duration_seconds = _histogram(
    "rest_http_request_duration_seconds",
    "REST HTTP request duration in seconds",
    ["module", "function", "status"],
)
