"""Дополнительная подготовка текста для TTS по шагам из конфигурации модели.

Порядок и набор шагов задаётся в ``ProviderLitserveTTSModelEntry.tts_input_steps``.
Базовая нормализация Unicode (``sanitize_text_for_speech_backend``) выполняется
до этих шагов в LitServe / batch-клиентах.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from core.utils.subdomain import TRANSLIT_MAP

_LATIN_A_Z = re.compile(r"[A-Za-z]+")


def _single_latin_to_cyrillic_table() -> dict[str, str]:
    groups: dict[str, list[str]] = {}
    for cyr, lat in TRANSLIT_MAP.items():
        if not cyr.islower():
            continue
        if cyr in ("ъ", "ь"):
            continue
        lat_l = lat.lower()
        if len(lat_l) != 1:
            continue
        groups.setdefault(lat_l, []).append(cyr)
    prefer_dup = {"e": "е", "y": "й"}
    table: dict[str, str] = {}
    for lat_ch, cyrs in groups.items():
        if len(cyrs) == 1:
            table[lat_ch] = cyrs[0]
        else:
            table[lat_ch] = prefer_dup.get(lat_ch, cyrs[0])
    table.update(
        {
            "q": "к",
            "w": "в",
            "c": "к",
            "j": "дж",
            "x": "кс",
        }
    )
    return table


_SINGLE_LATIN_TO_CYR = _single_latin_to_cyrillic_table()


def apply_silero_ru_latin_to_cyrillic(text: str) -> str:
    """Транслитерирует разряды латиницы ``[A-Za-z]+`` в кириллицу (чтение латиницей по таблице из :data:`TRANSLIT_MAP`).

    Диграфы (``sh``, ``sch`` и т.д.) намеренно **не** используются: для смеси EN/RU
    они ломают распространённые английские слова (например ``school`` → «щ…»).
    Остальной текст (пробелы, кириллица, цифры, знаки) не меняется.
    """

    def _run(word: str) -> str:
        lower = word.lower()
        parts: list[str] = []
        for ch in lower:
            rep = _SINGLE_LATIN_TO_CYR.get(ch)
            if rep is not None:
                parts.append(rep)
                continue
            if ch.isascii() and ch.isalpha():
                parts.append(ch)
                continue
            parts.append(ch)
        return "".join(parts)

    return _LATIN_A_Z.sub(lambda m: _run(m.group(0)), text)


TTS_INPUT_STEP_REGISTRY: dict[str, Callable[[str], str]] = {
    "silero_ru_latin_to_cyrillic": apply_silero_ru_latin_to_cyrillic,
}

TTS_INPUT_STEP_IDS: frozenset[str] = frozenset(TTS_INPUT_STEP_REGISTRY)


def apply_tts_input_steps(text: str, steps: Sequence[str]) -> str:
    out = text
    for step in steps:
        try:
            fn = TTS_INPUT_STEP_REGISTRY[step]
        except KeyError as exc:
            raise ValueError(f"Неизвестный tts_input_steps: {step!r}") from exc
        out = fn(out)
    return out


__all__ = [
    "TTS_INPUT_STEP_IDS",
    "TTS_INPUT_STEP_REGISTRY",
    "apply_silero_ru_latin_to_cyrillic",
    "apply_tts_input_steps",
]
