"""Нормализация чисел и числовых выражений для русского TTS.

Превращает цифровые последовательности в словесные:
    123 -> сто двадцать три
    3.14 -> три целых четырнадцать сотых
    100% -> сто процентов
"""

from __future__ import annotations

import re

from num2words import num2words


_INTEGER_RE = re.compile(r"\b(\d{1,3}(?:\s\d{3})*|\d+)\b")
_DECIMAL_RE = re.compile(r"\b(\d+)[.,](\d+)\b")
_PERCENT_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*%")
_ORDINAL_RE = re.compile(r"\b(\d+)-(?:й|я|е|го|му|м|ой|ую|их|ых|ми|ми)\b")


def _int_to_words(n: int) -> str:
    try:
        return num2words(n, lang="ru")
    except Exception:
        return str(n)


def _decimal_to_words(integer_part: str, frac_part: str) -> str:
    try:
        int_val = int(integer_part.replace(" ", ""))
        frac_val = int(frac_part)
        frac_len = len(frac_part)
        int_words = num2words(int_val, lang="ru")
        frac_words = num2words(frac_val, lang="ru")
        if frac_len == 1:
            denom = "десятых"
        elif frac_len == 2:
            denom = "сотых"
        elif frac_len == 3:
            denom = "тысячных"
        else:
            denom = "долей"
        return f"{int_words} целых {frac_words} {denom}"
    except Exception:
        return f"{integer_part},{frac_part}"


def _percent_to_words(value_str: str) -> str:
    value_str = value_str.replace(",", ".")
    try:
        if "." in value_str:
            int_part, frac_part = value_str.split(".", 1)
            return _decimal_to_words(int_part, frac_part) + " процентов"
        else:
            return _int_to_words(int(value_str)) + " процентов"
    except Exception:
        return value_str + " процентов"


def normalize_numbers_ru(text: str) -> str:
    """Переводит числовые выражения в тексте в слова (русский язык)."""
    result = _PERCENT_RE.sub(lambda m: _percent_to_words(m.group(1)), text)

    result = _DECIMAL_RE.sub(
        lambda m: _decimal_to_words(m.group(1), m.group(2)), result
    )

    result = _ORDINAL_RE.sub(
        lambda m: num2words(int(m.group(1)), to="ordinal", lang="ru"), result
    )

    result = _INTEGER_RE.sub(
        lambda m: _int_to_words(int(m.group(1).replace(" ", ""))), result
    )

    return result


__all__ = ["normalize_numbers_ru"]
