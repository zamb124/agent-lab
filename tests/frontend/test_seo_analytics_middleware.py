"""Юнит-тесты ``SeoAnalyticsMiddleware``: фильтры визитов и состав seo.visit."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest

from apps.frontend.seo import analytics_middleware
from core.config import get_settings
from core.logging import get_logger
from core.logging.setup import reset_logging_for_tests, setup_logging
from core.types import ASGIReceive, ASGIScope, ASGISend
from tests.fixtures.observability_log_capture import (
    caplog_record_dict,
    find_caplog_records,
)

_LOGGER_NAME = "apps.frontend.seo.analytics_middleware"


@pytest.fixture(scope="module", autouse=True)
def _seo_info_logging() -> Generator[None, None, None]:
    """structlog при LOGGING__LEVEL=WARNING не пишет INFO — для caplog поднимаем уровень."""
    settings = get_settings()
    warning_config = settings.logging
    info_config = warning_config.model_copy(update={"level": "INFO"})
    reset_logging_for_tests()
    setup_logging("pytest-seo-analytics", info_config)
    analytics_middleware.logger = get_logger(_LOGGER_NAME)
    yield
    reset_logging_for_tests()
    setup_logging("pytest", warning_config)


def _scope(path: str, *, method: str = "GET", query: bytes = b"",
           ua: str = "Mozilla/5.0 Chrome/121.0", ip: str = "8.8.8.8",
           referer: str = "") -> ASGIScope:
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


async def _run(scope: ASGIScope) -> list[ASGIScope]:
    """Прогнать middleware: app — реальный ASGI-эндпоинт, вернувший список вызовов."""
    calls: list[ASGIScope] = []

    async def app(inner_scope: ASGIScope, _receive: ASGIReceive, _send: ASGISend) -> None:
        calls.append(inner_scope)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message: dict[str, Any]) -> None:
        return None

    middleware = analytics_middleware.SeoAnalyticsMiddleware(app)
    await middleware(scope, receive, send)
    return calls


def _visit_fields(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [
        caplog_record_dict(rec)
        for rec in find_caplog_records(caplog, message="seo.visit", logger_name=_LOGGER_NAME)
    ]


@pytest.mark.asyncio
async def test_visit_logged_with_dimensions(caplog: pytest.LogCaptureFixture) -> None:
    calls = await _run(_scope("/products/rag", referer="https://google.com/q"))
    assert len(calls) == 1
    fields_list = _visit_fields(caplog)
    assert len(fields_list) == 1
    fields = fields_list[0]
    assert fields["surface"] == "page"
    assert fields["path"] == "/products/rag"
    assert fields["ua_family"] == "chrome"
    assert fields["bot"] is False
    assert fields["referer"] == "google.com"
    assert fields["host"] == "linnex.io"
    assert fields["visitor"]  # непустой псевдо-ид
    assert "ip" not in fields  # сырой IP в лог не уходит


@pytest.mark.asyncio
async def test_bot_visit_classified(caplog: pytest.LogCaptureFixture) -> None:
    await _run(_scope("/documentation/", ua="Mozilla/5.0 (compatible; YandexBot/3.0)"))
    fields_list = _visit_fields(caplog)
    assert len(fields_list) == 1
    fields = fields_list[0]
    assert fields["ua_family"] == "yandexbot"
    assert fields["bot"] is True
    assert fields["surface"] == "docs"


@pytest.mark.asyncio
@pytest.mark.parametrize("scope_kwargs", [
    {"method": "POST"},
    {"query": b"spa_shell=1"},
    {"ua": "HeadlessChrome/121.0"},
    {"ua": "seo-smoke/1.0"},
])
async def test_non_visit_skipped(
    scope_kwargs: dict[str, Any], caplog: pytest.LogCaptureFixture,
) -> None:
    calls = await _run(_scope("/products/rag", **scope_kwargs))
    assert len(calls) == 1  # запрос проходит дальше, просто без визита
    assert _visit_fields(caplog) == []


@pytest.mark.asyncio
async def test_private_path_skipped(caplog: pytest.LogCaptureFixture) -> None:
    await _run(_scope("/dashboard"))
    assert _visit_fields(caplog) == []
