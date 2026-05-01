"""Cloud.ru STT provider — обёртка над core/clients/stt_client.py для streaming-сценария."""

from __future__ import annotations

from typing import Any, Optional

from apps.voice.providers.base import BaseSTTProvider
from core.clients.stt_client import (
    BaseSTTClient,
    STTClientFactory,
    STTTranscriptionResult,
)
from core.logging import get_logger

logger = get_logger(__name__)


class CloudRuStreamSTTProvider(BaseSTTProvider):
    """Streaming STT через cloud.ru.

    Аккумулирует PCM-фреймы через push_audio. При вызове flush_buffer
    отправляет накопленное в cloud.ru и возвращает результат транскрипции.
    """

    SAMPLE_RATE: int = 16000

    def __init__(
        self,
        *,
        stt_client: Optional[BaseSTTClient] = None,
    ) -> None:
        self._stt_client = stt_client
        self._audio_buffer: bytearray = bytearray()

    def _ensure_client(self) -> BaseSTTClient:
        if self._stt_client is None:
            self._stt_client = STTClientFactory.create_client()
        return self._stt_client

    async def init(self, config: Optional[Any] = None) -> None:
        self._ensure_client()

    async def push_audio(self, chunk: bytes) -> None:
        self._audio_buffer.extend(chunk)

    async def flush_buffer(self) -> Optional[STTTranscriptionResult]:
        if not self._audio_buffer:
            return None
        data = bytes(self._audio_buffer)
        self._audio_buffer = bytearray()
        client = self._ensure_client()
        return await client.transcribe_audio(
            audio_bytes=data,
            file_name=f"voice_stream_{self.SAMPLE_RATE}.pcm",
            mime_type="audio/pcm",
            language=None,
        )

    def reset(self) -> None:
        self._audio_buffer = bytearray()

    def has_buffered_audio(self) -> bool:
        return len(self._audio_buffer) > 0
