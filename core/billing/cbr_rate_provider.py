"""
Провайдер актуального курса USD/RUB от официального API ЦБ РФ.

При старте сервиса делает один запрос к cbr.ru и затем обновляет курс каждые 5 минут
в фоне. При недоступности API используется fallback-значение из конфига
(billing.usd_to_rub_rate в conf.json).

Инициализация (в create_service_app._run_startup и в worker_startup):
    await refresh_rate_once(fallback=settings.billing.usd_to_rub_rate)
    run_with_log_context(
        refresh_loop_coro(fallback=settings.billing.usd_to_rub_rate),
        name="billing.cbr_rate_refresh",
        background_kind="startup",
    )
"""

import asyncio
import random
import xml.etree.ElementTree as ET
from datetime import date

import httpx

from core.logging import get_logger

logger = get_logger(__name__)

_CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
_REQUEST_TIMEOUT = 10.0

_cached_rate: float | None = None


def get_current_rate(fallback: float) -> float:
    """Возвращает последний успешно полученный курс USD/RUB.

    Если кэш ещё не заполнен (ЦБ не отвечал или refresh не вызывался),
    возвращает fallback из конфига.
    """
    if _cached_rate is not None:
        return _cached_rate
    return fallback


async def refresh_rate_once(fallback: float) -> None:
    """Делает один запрос к ЦБ и обновляет кэш.

    При любой ошибке сети или парсинга — предупреждение в лог,
    кэш не сбрасывается (остаётся предыдущее значение или None).
    """
    global _cached_rate

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get(_CBR_URL)
            _ = response.raise_for_status()
            rate, effective_date = _parse_usd_rate(response.text)

        _cached_rate = rate
        logger.info(
            "billing.cbr_rate.updated",
            usd_to_rub_rate=rate,
            effective_date=str(effective_date),
        )

    except httpx.HTTPStatusError as exc:
        logger.warning(
            "billing.cbr_rate.http_error",
            status_code=exc.response.status_code,
            url=str(exc.request.url),
            fallback=fallback,
        )
    except httpx.TransportError as exc:
        logger.warning(
            "billing.cbr_rate.network_error",
            error=str(exc),
            fallback=fallback,
        )
    except _CbrParseError as exc:
        logger.warning(
            "billing.cbr_rate.parse_error",
            error=str(exc),
            fallback=fallback,
        )
    except Exception as exc:
        logger.warning(
            "billing.cbr_rate.unexpected_error",
            **{"exception.type": type(exc).__name__},
            error=str(exc),
            fallback=fallback,
        )


async def refresh_loop_coro(fallback: float, interval: int = 300) -> None:
    """Бесконечный цикл обновления курса каждые `interval` секунд.

    Передавать в run_with_log_context — не запускать напрямую:
        run_with_log_context(
            refresh_loop_coro(fallback=..., interval=300),
            name="billing.cbr_rate_refresh",
            background_kind="startup",
        )

    Добавляет случайный jitter 0-10 сек к интервалу, чтобы несколько
    процессов не обращались к ЦБ синхронно.
    """
    while True:
        jitter = random.uniform(0, 10)
        await asyncio.sleep(interval + jitter)
        await refresh_rate_once(fallback=fallback)


class _CbrParseError(Exception):
    pass


def _parse_usd_rate(xml_text: str) -> tuple[float, date]:
    """Парсит XML-ответ ЦБ и возвращает (rate, effective_date).

    Raises:
        _CbrParseError: если структура XML не совпадает с ожидаемой.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise _CbrParseError(f"XML parse error: {exc}") from exc

    date_str = root.get("Date", "")
    try:
        effective_date = date(
            int(date_str[6:10]),
            int(date_str[3:5]),
            int(date_str[0:2]),
        )
    except (ValueError, IndexError) as exc:
        raise _CbrParseError(f"Неверный формат Date в ответе ЦБ: {date_str!r}") from exc

    for valute in root.findall("Valute"):
        char_code = valute.findtext("CharCode", "")
        if char_code != "USD":
            continue

        vunit_rate_text = valute.findtext("VunitRate", "")
        if not vunit_rate_text:
            value_text = valute.findtext("Value", "")
            nominal_text = valute.findtext("Nominal", "1")
            if not value_text:
                raise _CbrParseError("Нет ни VunitRate, ни Value для USD в ответе ЦБ")
            try:
                rate = float(value_text.replace(",", ".")) / float(nominal_text.replace(",", "."))
            except ValueError as exc:
                raise _CbrParseError(f"Не удалось разобрать Value/Nominal USD: {exc}") from exc
        else:
            try:
                rate = float(vunit_rate_text.replace(",", "."))
            except ValueError as exc:
                raise _CbrParseError(f"Не удалось разобрать VunitRate USD: {exc}") from exc

        if rate <= 0:
            raise _CbrParseError(f"Курс USD из ЦБ некорректен: {rate}")

        return rate, effective_date

    raise _CbrParseError("USD не найден в ответе ЦБ")
