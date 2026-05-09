"""Нормализация русских аббревиатур и сокращений перед TTS."""

from __future__ import annotations

import re

_ABBR_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bт\.е\.", re.IGNORECASE), "то есть"),
    (re.compile(r"\bт\.к\.", re.IGNORECASE), "так как"),
    (re.compile(r"\bи т\.д\.", re.IGNORECASE), "и так далее"),
    (re.compile(r"\bи т\.п\.", re.IGNORECASE), "и тому подобное"),
    (re.compile(r"\bи пр\.", re.IGNORECASE), "и прочее"),
    (re.compile(r"\bнапр\.", re.IGNORECASE), "например"),
    (re.compile(r"\bсм\.", re.IGNORECASE), "смотри"),
    (re.compile(r"\bср\.", re.IGNORECASE), "сравни"),
    (re.compile(r"\bпп\.", re.IGNORECASE), "пункты"),
    (re.compile(r"\bп\.", re.IGNORECASE), "пункт"),
    (re.compile(r"\bгг\.", re.IGNORECASE), "годы"),
    (re.compile(r"\bг\.", re.IGNORECASE), "год"),
    (re.compile(r"\bвв\.", re.IGNORECASE), "века"),
    (re.compile(r"\bв\.", re.IGNORECASE), "век"),
    (re.compile(r"\bтыс\.", re.IGNORECASE), "тысяч"),
    (re.compile(r"\bмлн\.", re.IGNORECASE), "миллионов"),
    (re.compile(r"\bмлрд\.", re.IGNORECASE), "миллиардов"),
    (re.compile(r"\bтрлн\.", re.IGNORECASE), "триллионов"),
    (re.compile(r"\bруб\.", re.IGNORECASE), "рублей"),
    (re.compile(r"\bкоп\.", re.IGNORECASE), "копеек"),
    (re.compile(r"\bкг\b", re.IGNORECASE), "килограмм"),
    (re.compile(r"\bгр\b", re.IGNORECASE), "грамм"),
    (re.compile(r"\bл\b"), "литр"),
    (re.compile(r"\bмл\b", re.IGNORECASE), "миллилитр"),
    (re.compile(r"\bкм\b", re.IGNORECASE), "километр"),
    (re.compile(r"\bм\b", re.IGNORECASE), "метр"),
    (re.compile(r"\bсм\b", re.IGNORECASE), "сантиметр"),
    (re.compile(r"\bмм\b", re.IGNORECASE), "миллиметр"),
    (re.compile(r"\bч\b"), "час"),
    (re.compile(r"\bмин\b", re.IGNORECASE), "минут"),
    (re.compile(r"\bсек\b", re.IGNORECASE), "секунд"),
]


def expand_abbreviations_ru(text: str) -> str:
    """Разворачивает распространённые русские аббревиатуры и сокращения."""
    for pattern, replacement in _ABBR_MAP:
        text = pattern.sub(replacement, text)
    return text


__all__ = ["expand_abbreviations_ru"]
