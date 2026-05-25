"""VAD-провайдер для тестового окружения — возвращает детерминированный результат."""

from typing import override

from apps.voice.providers.base import BaseVADProvider


class MockVADProvider(BaseVADProvider):
    """
    Тестовый VAD: обнаруживает речь, если в буфере ненулевые байты.
    Не загружает ML-моделей, не требует ML-зависимостей.
    """

    def __init__(self, always_speech: bool = True) -> None:
        self._always_speech: bool = always_speech

    @override
    async def detect_speech(self, audio_pcm: bytes, sample_rate: int) -> bool:
        _ = sample_rate
        if self._always_speech:
            return True
        return any(b != 0 for b in audio_pcm)

    @override
    def reset_state(self) -> None:
        pass
