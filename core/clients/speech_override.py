"""SpeechOverride: единый контракт per-call/per-process переопределения речи.

Один dataclass для STT/TTS/VAD. Любое не-None поле побеждает
per-company-настройку и deployment-default. Используется одинаково:

* в voice WS session — собирается из query/headers коннекта;
* в flows transcribe_node / tts_node — собирается из node.config;
* в eval-фасадах `transcribe_audio` / `synthesize_speech` —
  собирается из kwargs;
* в sync MediaTranscriber и CRM batch — собирается из параметров батча.

Резолв в трёх слоях (Zero-Guess, см. ``core.clients.voice_resolver``):

1. Per-call/per-process: значение поля из ``SpeechOverride``.
2. Per-company: запись в таблице ``company_voice_providers``.
3. Deployment-default: ``settings.voice.<kind>``.

Если итоговое значение пустое — ``raise ValueError`` (никаких неявных
дефолтов). См. ``speech_providers.mdc`` и ``architecture.mdc``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SpeechProviderName = Literal["litserve", "cloud_ru", "yandex", "sber", "mock"]
"""Каноничный набор имён провайдеров речи. Любое имя вне списка — фейл."""


VADProviderName = Literal["litserve", "silero_local", "mock"]
"""Каноничный набор имён VAD-провайдеров. ``silero_local`` — in-process
без сети к ``provider-litserve``."""


SpeechResponseFormat = Literal["wav", "mp3", "ogg", "pcm", "lpcm"]
"""Допустимые форматы аудио ответа TTS."""


class SpeechOverride(BaseModel):
    """Per-call/per-process переопределение настроек речи.

    Все поля — опциональны. Любое не-None побеждает то, что указано в
    ``company_voice_providers``, и ``settings.voice.<kind>``.

    Один объект используется тремя фабриками (STT/TTS/VAD); каждая
    читает только свои поля. Лишние поля игнорируются.
    """

    model_config = ConfigDict(extra="forbid")

    provider: SpeechProviderName | None = Field(
        default=None,
        description=(
            "Имя провайдера речи. Для VAD дополнительно допустим "
            "`silero_local` (см. ``VADProviderName``)."
        ),
    )
    model: str | None = Field(
        default=None,
        description=(
            "OpenAI-совместимый id модели у провайдера "
            "(например `gigaam-v3` для litserve STT, `kokoro-82m` для litserve TTS)."
        ),
    )
    voice: str | None = Field(
        default=None,
        description="Голос для TTS (например `alloy`, `af_bella`, `ermil`).",
    )
    language: str | None = Field(
        default=None,
        description="ISO-код языка для STT (например `ru`, `en`).",
    )
    sample_rate: int | None = Field(
        default=None,
        gt=0,
        description="Частота дискретизации для VAD/TTS (Гц).",
    )
    threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Порог детекции речи для VAD.",
    )
    response_format: SpeechResponseFormat | None = Field(
        default=None,
        description="Формат аудио ответа TTS.",
    )
    timeout_s: float | None = Field(
        default=None,
        gt=0.0,
        description="Таймаут одного HTTP-запроса в секундах.",
    )

    def is_empty(self) -> bool:
        """True если ни одно поле не задано — override фактически отсутствует."""
        return self.model_dump(exclude_none=True) == {}


__all__ = [
    "SpeechOverride",
    "SpeechProviderName",
    "VADProviderName",
    "SpeechResponseFormat",
]
