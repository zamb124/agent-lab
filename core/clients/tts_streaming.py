"""Streaming TTS контракт платформы.

Единый программный интерфейс для потокового синтеза речи. Используется:

* `apps/voice` — real-time voice сессия (text chunks → PCM → WebSocket).
* `apps/voice/api/synthesize` — HTTP с ``Transfer-Encoding: chunked``.
* `apps/flows` — code-узлы / tools, которым нужно озвучить стриминг текста.
* любой код платформы, который не хочет ждать полный текст для TTS.

Получение клиента — **только** через
``core.clients.voice_resolver.get_tts_streamer(*, company_id, override)``.
Прямой импорт конкретных реализаций вне `core/clients/**` запрещён CI.

Контракт:

* ``synthesize_chunk(text: str) -> bytes`` — синтез одного готового куска
  (чанкером уже порезано). Возвращает сырые аудиобайты (формат задан на
  этапе создания клиента).
* ``astream(text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]`` —
  принимает поток текста, возвращает поток аудио-чанков. Реализация по
  умолчанию использует ``VoiceChunker``-совместимую логику резки, ждёт
  первый speakable chunk и сразу отдаёт PCM, без ожидания полного текста.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from core.clients.tts_client import BaseTTSClient
from core.utils.text_sanitize import sanitize_text_for_speech_backend


class BaseTTSStreamer(ABC):
    """Базовый интерфейс потокового TTS-клиента."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Имя провайдера речи (для биллинга / логирования)."""

    @property
    @abstractmethod
    def mime_type(self) -> str:
        """MIME-тип чанков аудио, которые отдаёт ``astream`` / ``synthesize_chunk``."""

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """Частота дискретизации (Гц)."""

    @abstractmethod
    async def synthesize_chunk(self, text: str) -> bytes:
        """Синтезировать один готовый кусок текста → аудиобайты."""

    @abstractmethod
    async def astream(
        self,
        text_stream: AsyncIterator[str],
    ) -> AsyncIterator[bytes]:
        """Принять поток текста, отдать поток аудиочанков."""

    async def close(self) -> None:
        """Освободить ресурсы. По умолчанию — ничего."""


class BatchBackedTTSStreamer(BaseTTSStreamer):
    """Streaming адаптер поверх batch ``BaseTTSClient``.

    Внутри использует ``VoiceChunker`` для резки входного потока по
    синтаксическим границам и вызывает batch-TTS на каждый готовый кусок.
    Это даёт streaming-эффект (первый аудио-чанк уходит сразу после первой
    точки / предложения), не требуя от провайдера native streaming.
    """

    def __init__(
        self,
        *,
        tts_client: BaseTTSClient,
        response_format: str,
        sample_rate: int,
        provider_name: str,
        mime_type: str,
        chunk_max_chars: int = 100,
        min_words: int = 3,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("BatchBackedTTSStreamer: sample_rate должен быть > 0.")
        if provider_name == "":
            raise ValueError("BatchBackedTTSStreamer: provider_name обязателен.")
        if mime_type == "":
            raise ValueError("BatchBackedTTSStreamer: mime_type обязателен.")
        self._tts_client = tts_client
        self._response_format = response_format
        self._sample_rate = sample_rate
        self._provider = provider_name
        self._mime_type = mime_type
        self._chunk_max_chars = chunk_max_chars
        self._min_words = min_words

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def mime_type(self) -> str:
        return self._mime_type

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    async def synthesize_chunk(self, text: str) -> bytes:
        if not sanitize_text_for_speech_backend(text).strip():
            return b""
        result = await self._tts_client.synthesize(text=text)
        if len(result.audio_bytes) == 0:
            raise ValueError(
                "BatchBackedTTSStreamer.synthesize_chunk: провайдер вернул пустой audio_bytes "
                f"после успешного HTTP (provider={self._provider!r})."
            )
        return result.audio_bytes

    async def astream(
        self,
        text_stream: AsyncIterator[str],
    ) -> AsyncIterator[bytes]:
        from core.clients.voice_chunker import VoiceChunker

        chunker = VoiceChunker(
            chunk_max_chars=self._chunk_max_chars,
            min_words=self._min_words,
        )

        async for text_piece in text_stream:
            if not text_piece:
                continue
            chunks = chunker.feed(text_piece)
            for speakable in chunks:
                if not sanitize_text_for_speech_backend(speakable).strip():
                    continue
                audio = await self.synthesize_chunk(speakable)
                if audio:
                    yield audio

        tails = chunker.flush()
        for tail in tails:
            if not sanitize_text_for_speech_backend(tail).strip():
                continue
            audio = await self.synthesize_chunk(tail)
            if audio:
                yield audio


__all__ = [
    "BaseTTSStreamer",
    "BatchBackedTTSStreamer",
]
