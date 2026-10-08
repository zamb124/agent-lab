"""
Тесты провайдера курса USD/RUB от ЦБ РФ.

Покрывают парсинг XML и refresh_rate_once против локального HTTP,
который отдаёт тот же XML, что и scripts/XML_daily.asp.
"""

from __future__ import annotations

import socket

import pytest
from aiohttp import web

import core.billing.cbr_rate_provider as _provider
from core.billing.cbr_rate_provider import (
    _parse_usd_rate,
    get_current_rate,
    refresh_rate_once,
)
from tests.fixtures.aiohttp_ephemeral import ephemeral_web_server

# --- Хелпер сброса модульного кэша ---

@pytest.fixture(autouse=True)
def _reset_cached_rate():
    """Сбрасывает кэш перед каждым тестом, чтобы избежать утечек состояния."""
    _provider._cached_rate = None
    yield
    _provider._cached_rate = None


# --- Тестовые XML-ответы ---

_SAMPLE_XML = """\
<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="01.05.2026" name="Foreign Currency Market">
<Valute ID="R01235">
    <NumCode>840</NumCode>
    <CharCode>USD</CharCode>
    <Nominal>1</Nominal>
    <Name>Доллар США</Name>
    <Value>74,8014</Value>
    <VunitRate>74,8014</VunitRate>
</Valute>
<Valute ID="R01239">
    <NumCode>978</NumCode>
    <CharCode>EUR</CharCode>
    <Nominal>1</Nominal>
    <Name>Евро</Name>
    <Value>88,6429</Value>
    <VunitRate>88,6429</VunitRate>
</Valute>
</ValCurs>"""

_SAMPLE_XML_NO_VUNIT = """\
<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="01.05.2026" name="Foreign Currency Market">
<Valute ID="R01235">
    <NumCode>840</NumCode>
    <CharCode>USD</CharCode>
    <Nominal>2</Nominal>
    <Name>Доллар США</Name>
    <Value>149,6028</Value>
</Valute>
</ValCurs>"""

_SAMPLE_XML_NO_USD = """\
<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="01.05.2026" name="Foreign Currency Market">
<Valute ID="R01239">
    <NumCode>978</NumCode>
    <CharCode>EUR</CharCode>
    <Nominal>1</Nominal>
    <Name>Евро</Name>
    <Value>88,6429</Value>
    <VunitRate>88,6429</VunitRate>
</Valute>
</ValCurs>"""


# --- Парсинг XML ---

def test_parse_vunit_rate_with_comma():
    """VunitRate с запятой парсится в правильный float."""
    rate, effective_date = _parse_usd_rate(_SAMPLE_XML)

    assert rate == pytest.approx(74.8014)
    assert effective_date.year == 2026
    assert effective_date.month == 5
    assert effective_date.day == 1


def test_parse_value_over_nominal_fallback():
    """Когда VunitRate отсутствует, курс вычисляется как Value/Nominal."""
    rate, _ = _parse_usd_rate(_SAMPLE_XML_NO_VUNIT)

    assert rate == pytest.approx(74.8014)


def test_parse_raises_when_usd_absent():
    """Отсутствие USD в ответе ЦБ вызывает _CbrParseError."""
    with pytest.raises(_provider._CbrParseError, match="USD not found in CBR response"):
        _parse_usd_rate(_SAMPLE_XML_NO_USD)


def test_parse_raises_on_broken_xml():
    """Невалидный XML вызывает _CbrParseError."""
    with pytest.raises(_provider._CbrParseError, match="XML parse error"):
        _parse_usd_rate("<broken>")


def test_parse_raises_on_bad_date():
    """Неверный формат даты в атрибуте Date вызывает _CbrParseError."""
    xml = _SAMPLE_XML.replace('Date="01.05.2026"', 'Date="not-a-date"')
    with pytest.raises(_provider._CbrParseError, match="Invalid Date format"):
        _parse_usd_rate(xml)


def test_parse_raises_on_zero_rate():
    """Нулевой курс в VunitRate вызывает _CbrParseError."""
    xml = _SAMPLE_XML.replace(
        "<VunitRate>74,8014</VunitRate>",
        "<VunitRate>0</VunitRate>",
    )
    with pytest.raises(_provider._CbrParseError, match="USD rate from CBR is invalid"):
        _parse_usd_rate(xml)


# --- get_current_rate: fallback при пустом кэше ---

def test_get_current_rate_returns_fallback_when_cache_empty():
    """Если кэш пуст, возвращается fallback из аргумента."""
    assert _provider._cached_rate is None

    result = get_current_rate(fallback=85.0)

    assert result == pytest.approx(85.0)


def test_get_current_rate_returns_cached_value_ignoring_fallback():
    """Если кэш заполнен, возвращается кэшированное значение, а не fallback."""
    _provider._cached_rate = 90.5

    result = get_current_rate(fallback=85.0)

    assert result == pytest.approx(90.5)


def _closed_port_cbr_url() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    return f"http://127.0.0.1:{port}/scripts/XML_daily.asp"


def _cbr_app(status: int, body: str) -> web.Application:
    async def daily(_request: web.Request) -> web.Response:
        content_type = "application/xml" if status == 200 else "text/plain"
        return web.Response(status=status, text=body, content_type=content_type)

    app = web.Application()
    app.router.add_get("/scripts/XML_daily.asp", daily)
    return app


async def _refresh_from_local(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: int,
    body: str,
) -> None:
    async with ephemeral_web_server(_cbr_app(status, body)) as base_url:
        monkeypatch.setattr(_provider, "_CBR_URL", f"{base_url}/scripts/XML_daily.asp")
        await refresh_rate_once(fallback=85.0)


@pytest.mark.asyncio
async def test_refresh_rate_once_updates_cache_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    await _refresh_from_local(monkeypatch, status=200, body=_SAMPLE_XML)
    assert _provider._cached_rate == pytest.approx(74.8014)


@pytest.mark.asyncio
async def test_refresh_rate_once_keeps_old_cache_on_network_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _provider._cached_rate = 90.0
    monkeypatch.setattr(_provider, "_CBR_URL", _closed_port_cbr_url())
    await refresh_rate_once(fallback=85.0)
    assert _provider._cached_rate == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_refresh_rate_once_cache_stays_none_on_first_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _refresh_from_local(monkeypatch, status=503, body="Internal error")
    assert _provider._cached_rate is None
    assert get_current_rate(fallback=85.0) == pytest.approx(85.0)


@pytest.mark.asyncio
async def test_refresh_rate_once_keeps_old_cache_on_parse_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _provider._cached_rate = 92.3
    await _refresh_from_local(monkeypatch, status=200, body=_SAMPLE_XML_NO_USD)
    assert _provider._cached_rate == pytest.approx(92.3)


@pytest.mark.asyncio
async def test_refresh_rate_once_graceful_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    await _refresh_from_local(monkeypatch, status=503, body="Service Unavailable")
    assert _provider._cached_rate is None
