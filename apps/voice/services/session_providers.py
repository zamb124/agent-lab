"""Session-specific VAD/STT адаптеры voice-шлюза.

Клиенты речи создаются per-session через ``core.ai.runtime``. Класс хранит
deployment-default из ``VoiceServiceSettings`` и собирает streaming-адаптеры.
"""

from apps.voice.config import VoiceServiceSettings
from apps.voice.providers.base import BaseSTTProvider, BaseVADProvider
from apps.voice.providers.streaming_adapters import StreamingSTTProvider, StreamingVADProvider
from core.ai.runtime import (
    create_voice_stt_client,
    create_voice_vad_client,
    resolve_voice_stt_settings,
)
from core.clients.speech_override import SpeechOverride


class VoiceSessionProviders:
    """Фабрики streaming VAD/STT для одной voice-сессии."""

    def __init__(self, settings: VoiceServiceSettings) -> None:
        self.settings: VoiceServiceSettings = settings

    async def create_vad_provider(
        self,
        *,
        company_id: str,
        override: SpeechOverride | None = None,
    ) -> BaseVADProvider:
        vad_client = await create_voice_vad_client(company_id=company_id, override=override)
        vad_config = self.settings.voice.vad
        return StreamingVADProvider(
            vad_client=vad_client,
            sample_rate=vad_config.default_sample_rate,
            activation_threshold=vad_config.activation_threshold,
            deactivation_threshold=vad_config.deactivation_threshold,
            min_speech_ms=vad_config.min_speech_ms,
            min_silence_ms=vad_config.min_silence_ms,
            prefix_padding_ms=vad_config.prefix_padding_ms,
        )

    async def create_stt_provider(
        self,
        *,
        company_id: str,
        override: SpeechOverride | None = None,
    ) -> BaseSTTProvider:
        resolved = await resolve_voice_stt_settings(company_id=company_id, override=override)
        stt_client = await create_voice_stt_client(company_id=company_id, override=override)
        return StreamingSTTProvider(
            stt_client=stt_client,
            sample_rate=16000,
            language=resolved.language,
        )
