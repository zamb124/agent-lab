"""DI контейнер voice сервиса.

Не держит singleton'ов клиентов речи — клиенты создаются per-session
через ``core.clients.voice_resolver`` (tier-резолв
``SpeechOverride`` -> per-company -> deployment-default).

Контейнер хранит только настройки и фабрики session-specific VAD/STT
провайдеров-адаптеров. Потоковый TTS для voice-сессии получается
напрямую через ``voice_resolver.get_tts_streamer(...)`` и передаётся в
``speak_worker``: отдельной обёртки сверх batch-клиента не нужно.
"""

from __future__ import annotations

from apps.voice.config import get_voice_settings
from apps.voice.providers.base import (
    BaseSTTProvider,
    BaseVADProvider,
)
from apps.voice.providers.streaming_adapters import (
    StreamingSTTProvider,
    StreamingVADProvider,
)
from core.clients.speech_override import SpeechOverride
from core.clients.voice_resolver import (
    get_stt_client,
    get_vad_client,
    resolve_stt_settings,
)
from core.container import ContainerRegistry
from core.container.base import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class VoiceContainer(BaseContainer):
    """DI-контейнер voice сервиса.

    ``create_stt_provider`` / ``create_vad_provider`` — session-specific
    фабрики streaming-адаптеров над batch-клиентами из ``voice_resolver``.
    Для TTS в real-time сессии используйте ``get_tts_streamer`` напрямую.
    """

    @lazy
    def settings(self):
        return get_voice_settings()

    async def create_vad_provider(
        self,
        *,
        company_id: str,
        override: SpeechOverride | None = None,
    ) -> BaseVADProvider:
        vad_client = await get_vad_client(company_id=company_id, override=override)
        cfg = self.settings.voice.vad
        return StreamingVADProvider(
            vad_client=vad_client,
            sample_rate=cfg.default_sample_rate,
            activation_threshold=cfg.activation_threshold,
            deactivation_threshold=cfg.deactivation_threshold,
            min_speech_ms=cfg.min_speech_ms,
            min_silence_ms=cfg.min_silence_ms,
            prefix_padding_ms=cfg.prefix_padding_ms,
        )

    async def create_stt_provider(
        self,
        *,
        company_id: str,
        override: SpeechOverride | None = None,
    ) -> BaseSTTProvider:
        resolved = await resolve_stt_settings(company_id=company_id, override=override)
        stt_client = await get_stt_client(company_id=company_id, override=override)
        return StreamingSTTProvider(
            stt_client=stt_client,
            sample_rate=16000,
            language=resolved.language,
        )


_voice_registry: ContainerRegistry[VoiceContainer] = ContainerRegistry(
    VoiceContainer, name="VoiceContainer"
)

get_voice_container = _voice_registry.get
reset_voice_container = _voice_registry.reset
