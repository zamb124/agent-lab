"""Нормализация валют для русского TTS.

    100 руб. -> сто рублей
    100 ₽    -> сто рублей
    $100     -> сто долларов
    €100     -> сто евро
    100 USD  -> сто долларов
"""

from __future__ import annotations

import re

from num2words import num2words


def _num_to_words_ru(val: str) -> str:
    val = val.replace(" ", "").replace(",", ".")
    try:
        if "." in val:
            int_part, frac_part = val.split(".", 1)
            int_words = num2words(int(int_part), lang="ru")
            frac_words = num2words(int(frac_part), lang="ru")
            frac_len = len(frac_part)
            if frac_len == 1:
                denom = "десятых"
            elif frac_len == 2:
                denom = "сотых"
            else:
                denom = "долей"
            return f"{int_words} целых {frac_words} {denom}"
        return num2words(int(val), lang="ru")
    except Exception:
        return val


_CURRENCY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)\s*₽", re.IGNORECASE), "рублей"),
    (re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)\s*руб(?:ля|лей|лю|лём|ле)?\.?", re.IGNORECASE), "рублей"),
    (re.compile(r"\$\s*(\d[\d\s]*(?:[.,]\d+)?)"), "долларов"),
    (re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)\s*\$"), "долларов"),
    (re.compile(r"€\s*(\d[\d\s]*(?:[.,]\d+)?)"), "евро"),
    (re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)\s*€"), "евро"),
    (re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)\s*USD\b", re.IGNORECASE), "долларов"),
    (re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)\s*EUR\b", re.IGNORECASE), "евро"),
    (re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)\s*RUB\b", re.IGNORECASE), "рублей"),
    (re.compile(r"(\d[\d\s]*(?:[.,]\d+)?)\s*BTC\b", re.IGNORECASE), "биткоинов"),
]


def normalize_currencies_ru(text: str) -> str:
    """Переводит денежные суммы в тексте в словесную форму (русский язык)."""
    result = text
    for pattern, currency_word in _CURRENCY_PATTERNS:
        def _replace(m: re.Match[str], cw: str = currency_word) -> str:
            num_str = m.group(1)
            return f"{_num_to_words_ru(num_str)} {cw}"
        result = pattern.sub(_replace, result)
    return result


__all__ = ["normalize_currencies_ru"]
