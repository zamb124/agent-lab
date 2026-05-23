"""TTS-провайдер для тестового окружения — возвращает предсказуемые байты."""

from typing import Any

from apps.voice.providers.base import BaseTTSProvider


class MockTTSProvider(BaseTTSProvider):
    """
    Тестовый TTS: синтезирует текст в минимальный валидный PCM-буфер.
    Не загружает ML-моделей.
    """

    SAMPLE_RATE: int = 16000

    def __init__(self, bytes_per_char: int = 4) -> None:
        self._bytes_per_char = bytes_per_char
        self._synthesized_texts: list[str] = []

    async def init(self, config: Any | None = None) -> None:
        pass

    async def synthesize(self, text: str) -> bytes:
        self._synthesized_texts.append(text)
        # Возвращаем PCM-данные пропорциональные длине текста
        length = max(len(text) * self._bytes_per_char, 16)
        return bytes(range(256)) * (length // 256) + bytes(range(length % 256))

    @property
    def synthesized_texts(self) -> list[str]:
        return list(self._synthesized_texts)
