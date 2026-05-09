"""Нормализация дат для русского TTS.

Поддерживает форматы:
    YYYY-MM-DD -> «пятнадцатое января две тысячи двадцать шестого года»
    DD.MM.YYYY -> то же
    DD/MM/YYYY -> то же
    DD.MM.YY   -> то же (20xx)
"""

from __future__ import annotations

import re

from num2words import num2words


_MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

_ISO_DATE_RE = re.compile(
    r"\b(\d{4})-(\d{2})-(\d{2})\b"
)
_RU_DATE_RE = re.compile(
    r"\b(\d{1,2})[./](\d{1,2})[./](\d{2}(?:\d{2})?)\b"
)


def _day_to_ordinal(day: int) -> str:
    try:
        return num2words(day, to="ordinal", lang="ru")
    except Exception:
        return str(day)


def _year_to_words(year: int) -> str:
    try:
        return num2words(year, to="ordinal", lang="ru") + " года"
    except Exception:
        return str(year)


def _format_date(day: int, month: int, year: int) -> str:
    month_name = _MONTHS_RU.get(month)
    if month_name is None:
        return f"{day}.{month:02d}.{year}"
    day_words = _day_to_ordinal(day)
    year_words = _year_to_words(year)
    return f"{day_words} {month_name} {year_words}"


def _normalize_iso(m: re.Match[str]) -> str:
    try:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _format_date(day, month, year)
    except (ValueError, KeyError):
        return m.group(0)


def _normalize_ru_date(m: re.Match[str]) -> str:
    try:
        day, month = int(m.group(1)), int(m.group(2))
        yr_str = m.group(3)
        year = int(yr_str)
        if len(yr_str) == 2:
            year += 2000
        return _format_date(day, month, year)
    except (ValueError, KeyError):
        return m.group(0)


def normalize_dates_ru(text: str) -> str:
    """Переводит даты в тексте в словесную форму (русский язык)."""
    result = _ISO_DATE_RE.sub(_normalize_iso, text)
    result = _RU_DATE_RE.sub(_normalize_ru_date, result)
    return result


__all__ = ["normalize_dates_ru"]
