"""Единая точка текстовой нормализации для TTS.

``TextNormalizer`` применяет числа/даты/валюты/аббревиатуры согласно
``NormalizationConfig``. Вызывается из ``TtsTextPipeline`` на стадии 2.
"""

from __future__ import annotations

from core.clients.tts_pronunciation.models import NormalizationConfig
from core.utils.text_normalizers.abbreviations_ru import expand_abbreviations_ru
from core.utils.text_normalizers.currencies_ru import normalize_currencies_ru
from core.utils.text_normalizers.dates_ru import normalize_dates_ru
from core.utils.text_normalizers.numbers_ru import normalize_numbers_ru


class TextNormalizer:
    """Применяет текстовую нормализацию согласно конфигурации."""

    def normalize(self, text: str, config: NormalizationConfig) -> str:
        """Последовательно применяет включённые стадии нормализации.

        Порядок: аббревиатуры → даты → валюты → числа.
        Порядок важен: аббревиатуры разворачиваются первыми, пока они ещё
        не переписаны числовой нормализацией.
        """
        result = text
        locale = config.locale or "ru"

        if locale == "ru":
            if config.abbreviations:
                result = expand_abbreviations_ru(result)
            if config.dates:
                result = normalize_dates_ru(result)
            if config.currencies:
                result = normalize_currencies_ru(result)
            if config.numbers:
                result = normalize_numbers_ru(result)

        return result


_default_normalizer = TextNormalizer()


def get_text_normalizer() -> TextNormalizer:
    return _default_normalizer


__all__ = ["TextNormalizer", "get_text_normalizer"]
