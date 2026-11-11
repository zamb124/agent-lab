"""Юнит-тесты ``SeoAnalyticsMiddleware``: фильтры визитов и состав seo.visit."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from apps.frontend.seo import analytics_middleware


def _scope(path: str, *, method: str = "GET", query: bytes = b"",
           ua: str = "Mozilla/5.0 Chrome/121.0", ip: str = "8.8.8.8",
           referer: str = "") -> dict[str, Any]:
    headers = [
        (b"host", b"linnex.io"),
        (b"user-agent", ua.encode()),
        (b"x-forwarded-for", ip.encode()),
    ]
    if referer:
        headers.append((b"referer", referer.encode()))
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query,
        "headers": headers,
        "client": ("10.0.0.1", 1234),
    }


async def _run(scope: dict[str, Any]) -> dict[str, Any]:
    app = AsyncMock()
    with patch.object(analytics_middleware, "logger") as mock_logger:
        middleware = analytics_middleware.SeoAnalyticsMiddleware(app)
        await middleware(scope, AsyncMock(), AsyncMock())
    return app, mock_logger


@pytest.mark.asyncio
async def test_visit_logged_with_dimensions() -> None:
    app, mock_logger = await _run(
        _scope("/products/rag", referer="https://google.com/q"))
    app.assert_awaited_once()
    mock_logger.info.assert_called_once()
    event, kwargs = mock_logger.info.call_args[0][0], mock_logger.info.call_args[1]
    assert event == "seo.visit"
    assert kwargs["surface"] == "page"
    assert kwargs["path"] == "/products/rag"
    assert kwargs["ua_family"] == "chrome"
    assert kwargs["bot"] is False
    assert kwargs["referer"] == "google.com"
    assert kwargs["host"] == "linnex.io"
    assert kwargs["visitor"]  # непустой псевдо-ид
    assert "ip" not in kwargs  # сырой IP в лог не уходит


@pytest.mark.asyncio
async def test_bot_visit_classified() -> None:
    _, mock_logger = await _run(
        _scope("/documentation/", ua="Mozilla/5.0 (compatible; YandexBot/3.0)"))
    kwargs = mock_logger.info.call_args[1]
    assert kwargs["ua_family"] == "yandexbot"
    assert kwargs["bot"] is True
    assert kwargs["surface"] == "docs"


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_kwargs", [
    {"method": "POST"},
    {"query": b"spa_shell=1"},
    {"ua": "HeadlessChrome/121.0"},
    {"ua": "seo-smoke/1.0"},
])
async def test_non_visit_skipped(scope_kwargs: dict[str, Any]) -> None:
    app, mock_logger = await _run(_scope("/products/rag", **scope_kwargs))
    app.assert_awaited_once()  # запрос проходит дальше, просто без визита
    mock_logger.info.assert_not_called()


@pytest.mark.asyncio
async def test_private_path_skipped() -> None:
    _, mock_logger = await _run(_scope("/dashboard"))
    mock_logger.info.assert_not_called()
