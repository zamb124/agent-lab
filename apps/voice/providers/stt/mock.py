"""STT-провайдер для тестового окружения — возвращает фиксированную транскрипцию."""

from typing import Any

from apps.voice.providers.base import BaseSTTProvider
from core.clients.stt_client import STTTranscriptionResult
from core.files.models import AudioTranscriptionStatus


class MockSTTProvider(BaseSTTProvider):
    """
    Тестовый STT: при каждом flush возвращает заданный текст.
    Не делает HTTP-запросов, не требует ключей API.
    """

    def __init__(self, text: str = "тестовая транскрипция") -> None:
        self._text = text
        self._buffer: bytes = b""
        self._call_count: int = 0

    async def init(self, config: Any | None = None) -> None:
        pass

    async def push_audio(self, chunk: bytes) -> None:
        self._buffer += chunk

    async def flush_buffer(self) -> STTTranscriptionResult | None:
        if not self._buffer:
            return None
        self._buffer = b""
        self._call_count += 1
        return STTTranscriptionResult(
            provider="mock",
            status=AudioTranscriptionStatus.DONE,
            text=self._text,
        )

    def reset(self) -> None:
        self._buffer = b""

    @property
    def call_count(self) -> int:
        return self._call_count
