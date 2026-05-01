"""DI контейнер voice сервиса."""

from __future__ import annotations

from typing import Optional

from core.container.base import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class VoiceContainer(BaseContainer):
    """DI-контейнер voice сервиса.

    Провайдер STT/TTS/VAD выбирается по значению `voice.stt.provider` / `voice.tts.provider` /
    `voice.vad.model` из конфига: для production — реальные, для тестов — mock.
    """

    @lazy
    def settings(self):
        from apps.voice.config import get_voice_settings

        return get_voice_settings()

    @lazy
    def vad_provider(self):
        model = self.settings.vad.model
        if model == "mock":
            from apps.voice.providers.vad.mock import MockVADProvider

            return MockVADProvider()
        from apps.voice.providers.vad.silero import SileroVADProvider

        return SileroVADProvider(
            sample_rate=self.settings.vad.sample_rate,
            threshold=self.settings.vad.threshold,
        )

    @lazy
    def stt_provider(self):
        provider = self.settings.stt.provider
        if provider == "mock":
            from apps.voice.providers.stt.mock import MockSTTProvider

            return MockSTTProvider(text=self.settings.stt.mock_text)
        from apps.voice.providers.stt.cloud_ru import CloudRuStreamSTTProvider

        return CloudRuStreamSTTProvider()

    @lazy
    def tts_provider(self):
        provider = self.settings.tts.provider
        if provider == "mock":
            from apps.voice.providers.tts.mock import MockTTSProvider

            return MockTTSProvider()
        from apps.voice.providers.tts.kokoro_local import KokoroLocalTTSProvider

        return KokoroLocalTTSProvider(
            sample_rate=self.settings.tts.kokoro_sample_rate,
            accelerator=self.settings.tts.kokoro_accelerator,
        )


_voice_container: Optional[VoiceContainer] = None


def get_voice_container() -> VoiceContainer:
    global _voice_container
    if _voice_container is None:
        _voice_container = VoiceContainer()
        logger.info("VoiceContainer инициализирован")
    return _voice_container


def reset_voice_container() -> None:
    global _voice_container
    _voice_container = None
