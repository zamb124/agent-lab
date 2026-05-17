"""Базовые интерфейсы провайдеров STT/TTS/VAD."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from core.clients.stt_client import STTTranscriptionResult


class BaseVADProvider(ABC):
    """Детекция речи (Voice Activity Detection)."""

    @abstractmethod
    async def detect_speech(self, audio_pcm: bytes, sample_rate: int) -> bool:
        """Вернуть True если в аудиофрейме есть речь."""

    @abstractmethod
    def reset_state(self) -> None:
        """Сбросить внутреннее состояние модели (после тишины/barge-in)."""

    def consume_preroll(self) -> bytes:
        """Забрать pre-roll PCM, если конкретный VAD его накапливает."""
        return b""

    async def close(self) -> None:
        """Освободить ресурсы. По умолчанию — ничего не делает."""


class BaseSTTProvider(ABC):
    """Потоковое распознавание речи (Speech-to-Text).

    Провайдер накапливает аудио через push_audio, итоговая транскрипция
    возвращается через flush_buffer при окончании фрагмента речи.
    """

    @abstractmethod
    async def init(self, config: Optional[Any] = None) -> None:
        """Инициализировать соединение / загрузить модель."""

    @abstractmethod
    async def push_audio(self, chunk: bytes) -> None:
        """Добавить очередной PCM-фрейм в буфер."""

    @abstractmethod
    async def flush_buffer(self) -> Optional[STTTranscriptionResult]:
        """Сбросить буфер и вернуть итоговую транскрипцию (или None если нет аудио)."""

    @abstractmethod
    def reset(self) -> None:
        """Сбросить буфер без распознавания (при barge-in)."""

    async def peek_transcript(
        self, *, min_buffer_bytes: int = 16000
    ) -> Optional[STTTranscriptionResult]:
        """Получить промежуточный transcript без сброса буфера (chunked-batch).

        По умолчанию провайдер не поддерживает partial — возвращает ``None``,
        и ``stt_worker`` не пытается слать ``transcript final=False``.
        Реализация в ``StreamingSTTProvider`` запускает batch-распознавание
        текущего PCM, не очищая буфер.
        """
        return None

    async def close(self) -> None:
        """Освободить ресурсы. По умолчанию — ничего не делает."""


class BaseTTSProvider(ABC):
    """Синтез речи (Text-to-Speech)."""

    @abstractmethod
    async def init(self, config: Optional[Any] = None) -> None:
        """Загрузить модель синтезатора."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Синтезировать текст в PCM-байты."""

    async def close(self) -> None:
        """Освободить ресурсы. По умолчанию — ничего не делает."""
