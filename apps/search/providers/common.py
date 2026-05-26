"""Provider parsing helpers."""

from __future__ import annotations

import time
from urllib.parse import urlsplit

from core.search import MetaSearchProviderStatus


def string_field(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def int_rank(value: object, *, default: int) -> int:
    return value if isinstance(value, int) and value >= 1 else default


def display_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    if len(path) > 42:
        path = f"{path[:39]}..."
    return f"{host}{path}"


def provider_status(
    started: float,
    *,
    ok: bool,
    results_count: int = 0,
    error: str | None = None,
) -> MetaSearchProviderStatus:
    return MetaSearchProviderStatus(
        ok=ok,
        latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
        results_count=results_count,
        error=error,
    )
