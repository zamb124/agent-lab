"""TTS Pronunciation Shaping Engine.

Единая точка текстового препроцесса перед синтезом речи — применяется один раз
в ``PronunciationAwareTTSClient`` для всех провайдеров. Поддерживает:

* **Alias-правила** — точная подстрока с word-boundary (Aho-Corasick, O(N)).
* **Regex-правила** — precompiled `re.Pattern`, применяются по порядку.
* **Stress-маркеры** — символ ``+`` перед ударной гласной; только для
  провайдеров из ``STRESS_CAPABLE_PROVIDERS`` (Silero/Yandex/Sber).
* **Нормализация** — числа, даты, валюты, аббревиатуры через ``num2words``
  и встроенные словари.

Cascade источников правил:
    platform_pronunciation_rules (system/superadmin)
    → company_pronunciation_rules (per-company)
    → SpeechOverride.pronunciation_rules (per-call)

Точка входа: ``TtsTextPipeline`` из ``.pipeline``.
"""

from core.clients.tts_pronunciation.models import (
    PROVIDER_CAPABILITIES,
    STRESS_CAPABLE_PROVIDERS,
    CompiledPronunciation,
    NormalizationConfig,
    PronunciationRule,
    PronunciationRuleSet,
    ProviderCapabilities,
)
from core.clients.tts_pronunciation.pipeline import TtsTextPipeline

__all__ = [
    "CompiledPronunciation",
    "NormalizationConfig",
    "PROVIDER_CAPABILITIES",
    "STRESS_CAPABLE_PROVIDERS",
    "PronunciationRule",
    "PronunciationRuleSet",
    "ProviderCapabilities",
    "TtsTextPipeline",
]
