"""
Unit-тесты провайдера курса USD/RUB от ЦБ РФ.

Покрывают:
- парсинг XML (VunitRate и Value/Nominal, запятая как разделитель),
- effective_date из атрибута Date,
- fallback при пустом кэше и при ошибках сети/парсинга,
- сохранение последнего успешного курса при неудачном refresh,
- базовые граничные случаи (USD отсутствует, rate <= 0).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import core.billing.cbr_rate_provider as _provider
from core.billing.cbr_rate_provider import (
    _parse_usd_rate,
    get_current_rate,
    refresh_rate_once,
)


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
    with pytest.raises(_provider._CbrParseError, match="USD не найден"):
        _parse_usd_rate(_SAMPLE_XML_NO_USD)


def test_parse_raises_on_broken_xml():
    """Невалидный XML вызывает _CbrParseError."""
    with pytest.raises(_provider._CbrParseError, match="XML parse error"):
        _parse_usd_rate("<broken>")


def test_parse_raises_on_bad_date():
    """Неверный формат даты в атрибуте Date вызывает _CbrParseError."""
    xml = _SAMPLE_XML.replace('Date="01.05.2026"', 'Date="not-a-date"')
    with pytest.raises(_provider._CbrParseError, match="Неверный формат Date"):
        _parse_usd_rate(xml)


def test_parse_raises_on_zero_rate():
    """Нулевой курс в VunitRate вызывает _CbrParseError."""
    xml = _SAMPLE_XML.replace(
        "<VunitRate>74,8014</VunitRate>",
        "<VunitRate>0</VunitRate>",
    )
    with pytest.raises(_provider._CbrParseError, match="некорректен"):
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


# --- Хелпер для создания mock AsyncClient ---

def _make_client_mock(text: str, status_code: int = 200) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.text = text
    response.status_code = status_code
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=response,
        )
    else:
        response.raise_for_status.return_value = None

    client_mock = AsyncMock()
    client_mock.get = AsyncMock(return_value=response)
    client_mock.__aenter__ = AsyncMock(return_value=client_mock)
    client_mock.__aexit__ = AsyncMock(return_value=False)
    return client_mock


# --- refresh_rate_once ---

@pytest.mark.asyncio
async def test_refresh_rate_once_updates_cache_on_success():
    """Успешный ответ ЦБ обновляет кэш реальным курсом."""
    client_mock = _make_client_mock(_SAMPLE_XML)

    with patch("httpx.AsyncClient", return_value=client_mock):
        await refresh_rate_once(fallback=85.0)

    assert _provider._cached_rate == pytest.approx(74.8014)


@pytest.mark.asyncio
async def test_refresh_rate_once_keeps_old_cache_on_network_error():
    """При сетевой ошибке предыдущий кэш сохраняется."""
    _provider._cached_rate = 90.0

    with patch("httpx.AsyncClient") as cls_mock:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.get = AsyncMock(side_effect=httpx.ConnectError("no route"))
        cls_mock.return_value = instance

        await refresh_rate_once(fallback=85.0)

    assert _provider._cached_rate == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_refresh_rate_once_cache_stays_none_on_first_error():
    """При ошибке и пустом кэше кэш остаётся None; get_current_rate возвращает fallback."""
    client_mock = _make_client_mock("Internal error", status_code=503)

    with patch("httpx.AsyncClient", return_value=client_mock):
        await refresh_rate_once(fallback=85.0)

    assert _provider._cached_rate is None
    assert get_current_rate(fallback=85.0) == pytest.approx(85.0)


@pytest.mark.asyncio
async def test_refresh_rate_once_keeps_old_cache_on_parse_error():
    """При ошибке парсинга (USD отсутствует) старый кэш не сбрасывается."""
    _provider._cached_rate = 92.3
    client_mock = _make_client_mock(_SAMPLE_XML_NO_USD)

    with patch("httpx.AsyncClient", return_value=client_mock):
        await refresh_rate_once(fallback=85.0)

    assert _provider._cached_rate == pytest.approx(92.3)


@pytest.mark.asyncio
async def test_refresh_rate_once_graceful_on_http_error():
    """HTTP-ошибка не поднимает исключение — только warning в лог."""
    client_mock = _make_client_mock("Service Unavailable", status_code=503)

    with patch("httpx.AsyncClient", return_value=client_mock):
        await refresh_rate_once(fallback=85.0)  # не должно поднять исключение

    assert _provider._cached_rate is None
