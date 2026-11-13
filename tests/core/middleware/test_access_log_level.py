"""AccessLog severity-таксономия: 5xx — отказ платформы, 4xx — исход клиента."""

from __future__ import annotations

import logging

from core.middleware.access_log import AccessLogMiddleware


def test_access_log_level_for_status() -> None:
    level = AccessLogMiddleware._level_for_status  # pyright: ignore[reportPrivateUsage]

    assert level(200, "/api/items") == logging.INFO
    assert level(301, "/") == logging.INFO
    # 4xx — корректная работа границы (сканеры, auth, rate-limit) → INFO.
    assert level(401, "/api/items") == logging.INFO
    assert level(403, "/api/items") == logging.INFO
    assert level(404, "/.env") == logging.INFO
    assert level(405, "/api/items") == logging.INFO
    assert level(429, "/api/items") == logging.INFO
    # Служебные пути UI — шум ниже INFO.
    assert level(404, "/static/missing.js") == logging.DEBUG
    # 5xx — отказ платформы.
    assert level(500, "/api/items") == logging.ERROR
    assert level(503, "/api/items") == logging.ERROR
