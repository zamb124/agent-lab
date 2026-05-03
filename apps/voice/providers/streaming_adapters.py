"""Универсальные streaming-адаптеры для STT/TTS/VAD voice сессии.

Эти адаптеры — единственный способ оборачивать batch-клиента из
`core.clients.{stt,tts,vad}_client` в streaming-интерфейс
`apps.voice.providers.base.{BaseSTTProvider,BaseTTSProvider,BaseVADProvider}`.

Не привязаны к провайдеру: внутрь передаётся уже резолвнутый клиент
(`BaseSTTClient` / `BaseTTSClient` / `BaseVADClient`), полученный через
`core.clients.voice_resolver.get_*_client(*, company_id, override)`.
Сами провайдеры — `litserve` (provider-litserve), `cloud_ru`, `yandex`,
`sber` для STT/TTS, `litserve`/`silero_local` для VAD — об этом не знают.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from apps.voice.providers.base import (
    BaseSTTProvider,
    BaseTTSProvider,
    BaseVADProvider,
)
from core.clients.stt_client import BaseSTTClient, STTTranscriptionResult
from core.clients.tts_client import BaseTTSClient
from core.clients.vad_client import BaseVADClient
from core.logging import get_logger


logger = get_logger(__name__)


_FRAME_DURATION_S = 0.02


class StreamingSTTProvider(BaseSTTProvider):
    """Streaming STT через любой `BaseSTTClient`.

    Аккумулирует PCM-фреймы в буфере (`push_audio`); при `flush_buffer`
    отправляет накопленное в batch-клиент и возвращает результат.
    """

    def __init__(
        self,
        *,
        stt_client: BaseSTTClient,
        sample_rate: int = 16000,
        language: Optional[str] = None,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("StreamingSTTProvider: sample_rate должен быть > 0.")
        self._stt_client = stt_client
        self._sample_rate = sample_rate
        self._language = language
        self._audio_buffer: bytearray = bytearray()

    async def init(self, config: Optional[Any] = None) -> None:
        return None

    async def push_audio(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._audio_buffer.extend(chunk)

    async def flush_buffer(self) -> Optional[STTTranscriptionResult]:
        if not self._audio_buffer:
            return None
        data = bytes(self._audio_buffer)
        self._audio_buffer = bytearray()
        return await self._stt_client.transcribe_audio(
            audio_bytes=data,
            file_name=f"voice_stream_{self._sample_rate}.pcm",
            mime_type="audio/pcm",
            language=self._language,
        )

    def reset(self) -> None:
        self._audio_buffer = bytearray()

    def has_buffered_audio(self) -> bool:
        return len(self._audio_buffer) > 0


class StreamingTTSProvider(BaseTTSProvider):
    """Streaming TTS через любой `BaseTTSClient`.

    `synthesize(text)` вызывает batch `tts_client.synthesize(...)` и
    возвращает сырые audio bytes; формат / голос / sample_rate уже
    зафиксированы в batch-клиенте при создании через resolver.
    """

    def __init__(self, *, tts_client: BaseTTSClient) -> None:
        self._tts_client = tts_client
        self._initialized = False

    async def init(self, config: Optional[Any] = None) -> None:
        self._initialized = True

    async def synthesize(self, text: str) -> bytes:
        if not self._initialized:
            raise RuntimeError("StreamingTTSProvider не инициализирован (вызовите init).")
        if text == "":
            raise ValueError("StreamingTTSProvider: пустой text.")
        result = await self._tts_client.synthesize(text=text)
        return result.audio_bytes

    async def close(self) -> None:
        self._initialized = False


class StreamingVADProvider(BaseVADProvider):
    """Streaming VAD через любой `BaseVADClient`.

    Накапливает PCM-фреймы внутри окна (`window_ms`, по умолчанию 200ms)
    и периодически вызывает `vad_client.detect_segments()`. Возвращает
    `True` если в окне найдена речь.
    """

    def __init__(
        self,
        *,
        vad_client: BaseVADClient,
        sample_rate: int = 16000,
        threshold: Optional[float] = None,
        window_ms: int = 200,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("StreamingVADProvider: sample_rate должен быть > 0.")
        if window_ms <= 0:
            raise ValueError("StreamingVADProvider: window_ms должен быть > 0.")
        self._vad_client = vad_client
        self._sample_rate = sample_rate
        self._threshold = threshold
        self._window_bytes = int(sample_rate * 2 * window_ms / 1000)
        self._buffer: bytearray = bytearray()
        self._lock = asyncio.Lock()

    async def detect_speech(self, audio_pcm: bytes, sample_rate: int) -> bool:
        if sample_rate != self._sample_rate:
            raise ValueError(
                f"StreamingVADProvider: ожидается sample_rate={self._sample_rate}, "
                f"получено {sample_rate}."
            )
        async with self._lock:
            self._buffer.extend(audio_pcm)
            if len(self._buffer) < self._window_bytes:
                return False

            audio_window = bytes(self._buffer)
            self._buffer = bytearray()

        segments = await self._vad_client.detect_segments(
            audio_bytes=audio_window,
            sample_rate=self._sample_rate,
            threshold=self._threshold,
        )
        return len(segments) > 0

    def reset_state(self) -> None:
        self._buffer = bytearray()


__all__ = [
    "StreamingSTTProvider",
    "StreamingTTSProvider",
    "StreamingVADProvider",
]
