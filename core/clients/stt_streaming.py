"""Streaming STT контракт платформы.

Единый программный интерфейс для потокового распознавания речи. Используется:

* `apps/voice` — внутри real-time voice сессии (микрофон → PCM → STT);
* `apps/flows` — в tools / code-узлах, где нужно стримить speech-to-text без
  batch-вызова;
* любой другой код платформы, которому нужен streaming STT.

Получение клиента — **только** через
``core.clients.voice_resolver.get_stt_streamer(*, company_id, override)``.
Прямой импорт конкретных реализаций вне `core/clients/**` запрещён CI
(`scripts/check_voice_resolver_usage.py`).

Контракт:

* ``push_audio(chunk: bytes)`` — подать очередной PCM-фрейм (16-bit mono).
* ``flush()`` → ``STTTranscriptionResult | None`` — завершить фрагмент и
  получить финальную транскрипцию. Возвращает ``None``, если буфер пуст.
* ``reset()`` — очистить буфер без транскрибации (используется при barge-in).
* ``close()`` — освободить ресурсы.

Асинхронный iterator ``astream(audio_chunks, sample_rate)`` — обёртка для
случаев, когда источник аудио уже представлен как ``AsyncIterator[bytes]``:
адаптер кормит каждое значение через ``push_audio``; единственный финальный
результат отдаётся при закрытии итератора входа.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from core.clients.stt_client import BaseSTTClient, STTTranscriptionResult
from core.files.media.pcm_to_wav import pcm_s16le_mono_to_wav
from core.logging import get_logger

logger = get_logger(__name__)


class BaseSTTStreamer(ABC):
    """Базовый интерфейс потокового STT-клиента (push-based)."""

    @abstractmethod
    async def push_audio(self, chunk: bytes) -> None:
        """Добавить очередной PCM-фрейм в буфер."""

    @abstractmethod
    async def flush(self) -> Optional[STTTranscriptionResult]:
        """Сбросить буфер и вернуть итоговую транскрипцию (``None`` если аудио нет)."""

    @abstractmethod
    def reset(self) -> None:
        """Сбросить буфер без транскрипции (barge-in)."""

    async def close(self) -> None:
        """Освободить ресурсы. По умолчанию — ничего не делает."""

    async def astream(
        self,
        audio_chunks: AsyncIterator[bytes],
    ) -> AsyncIterator[STTTranscriptionResult]:
        """Пропустить через себя поток PCM и отдать все финальные транскрипции.

        Реализация по умолчанию: накопить весь поток и сделать один ``flush``
        в конце. Провайдеры, умеющие native streaming (partial/final), могут
        переопределить метод.
        """
        async for chunk in audio_chunks:
            if chunk:
                await self.push_audio(chunk)
        result = await self.flush()
        if result is not None:
            yield result


class BufferedSTTStreamer(BaseSTTStreamer):
    """Streaming адаптер поверх batch ``BaseSTTClient``.

    Накапливает PCM в памяти и при ``flush`` делает один batch-вызов
    `transcribe_audio`. Для провайдеров, которые не имеют native streaming
    (cloud_ru, litserve в синхронном режиме) — это единственный способ
    интегрировать их в streaming-pipeline voice сессии.
    """

    def __init__(
        self,
        *,
        stt_client: BaseSTTClient,
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("BufferedSTTStreamer: sample_rate должен быть > 0.")
        self._stt_client = stt_client
        self._sample_rate = sample_rate
        self._language = language
        self._buffer: bytearray = bytearray()

    async def push_audio(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._buffer.extend(chunk)

    async def flush(self) -> Optional[STTTranscriptionResult]:
        if not self._buffer:
            return None
        pcm = bytes(self._buffer)
        self._buffer = bytearray()
        wav = pcm_s16le_mono_to_wav(pcm, sample_rate=self._sample_rate)
        return await self._stt_client.transcribe_audio(
            audio_bytes=wav,
            file_name="voice_segment.wav",
            mime_type="audio/wav",
            language=self._language,
        )

    def reset(self) -> None:
        self._buffer = bytearray()

    @property
    def has_buffered_audio(self) -> bool:
        return len(self._buffer) > 0


__all__ = [
    "BaseSTTStreamer",
    "BufferedSTTStreamer",
]
