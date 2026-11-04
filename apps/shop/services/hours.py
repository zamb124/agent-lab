"""Часы работы витрины: открыт ли магазин `сейчас` и когда откроется.

Формат ``shop.working_hours``: ``{"0": "09:00-22:00", ..., "6": "11:00-18:00"}``
— ключ дня недели (0=Пн … 6=Вс), значение ``"HH:MM-HH:MM"`` в локальном
времени ``shop.timezone``. ``om == cm`` — выходной; ``om > cm`` — overnight
интервал через полночь (открыт до ``cm`` следующего дня).

Зеркало JS-логики ``hoursBadge()`` в storefront_shell.py — сервер и витрина
обязаны решать одинаково, иначе витрина разрешит то, что отклонит сервер.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.types import JsonValue

_DEFAULT_TZ = "Europe/Moscow"
_DAYS_RU = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


class OpenState(NamedTuple):
    open: bool
    next_open: str | None  # «в 09:00», «завтра в 09:00», «Сб в 11:00»


def _parse_range(value: JsonValue | None) -> tuple[int, int] | None:
    """"HH:MM-HH:MM" → (open_min, close_min) или None при мусоре."""
    if not isinstance(value, str):
        return None
    parts = value.split("-")
    if len(parts) != 2:
        return None
    try:
        oh, oh_m = (int(x) for x in parts[0].split(":", 1))
        ch, ch_m = (int(x) for x in parts[1].split(":", 1))
    except (ValueError, IndexError):
        return None
    if not (0 <= oh <= 23 and 0 <= oh_m <= 59 and 0 <= ch <= 23 and 0 <= ch_m <= 59):
        return None
    om, cm = oh * 60 + oh_m, ch * 60 + ch_m
    if om == cm:  # "00:00-00:00" — выходной, а не круглосуточно
        return None
    return om, cm


def _tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or _DEFAULT_TZ)
    except ZoneInfoNotFoundError:
        return ZoneInfo(_DEFAULT_TZ)


def shop_open_state(
    working_hours: Mapping[str, JsonValue] | None,
    tz_name: str | None,
    now: datetime,
) -> OpenState:
    """Открыт ли магазин сейчас; next_open — ближайшее открытие для сообщений."""
    if not working_hours:
        return OpenState(True, None)
    local = now.astimezone(_tz(tz_name))
    day = local.weekday()  # 0=Пн … 6=Вс — как ключи working_hours
    mins = local.hour * 60 + local.minute

    def rng(d: int) -> tuple[int, int] | None:
        return _parse_range(working_hours.get(str(d)))

    # Overnight-остаток вчерашнего дня: "22:00-06:00" держит открытым до 06:00.
    prev = rng((day - 1) % 7)
    if prev is not None and prev[0] > prev[1] and mins < prev[1]:
        return OpenState(True, None)

    today = rng(day)
    if today is not None:
        om, cm = today
        label = f"{om // 60:02d}:{om % 60:02d}"
        if om < cm:
            if om <= mins < cm:
                return OpenState(True, None)
            if mins < om:
                return OpenState(False, f"в {label}")
        else:  # om > cm — overnight: вечер ≥om открыт, день до om ждёт
            return (
                OpenState(True, None)
                if mins >= om
                else OpenState(False, f"в {label}")
            )

    # Ищем ближайший следующий день с рабочим интервалом (до 7 вперёд).
    for offset in range(1, 8):
        nd = (day + offset) % 7
        nxt = rng(nd)
        if nxt is not None:
            label = f"{nxt[0] // 60:02d}:{nxt[0] % 60:02d}"
            if offset == 1:
                return OpenState(False, f"завтра в {label}")
            return OpenState(False, f"{_DAYS_RU[nd]} в {label}")
    # working_hours задан, но ни одного валидного интервала — считаем закрытым
    # навсегда (магазин «временно не работает»), next_open неизвестно.
    return OpenState(False, None)
