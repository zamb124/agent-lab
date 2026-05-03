"""DI контейнер voice сервиса.

Не держит singleton'ов клиентов речи — клиенты создаются per-session
через `core.clients.voice_resolver` (tier-резолв
override -> per-company -> deployment-default).

Контейнер хранит только настройки и фабрики session-specific
streaming-провайдеров (адаптеров над batch-клиентами).
"""

from __future__ import annotations

from typing import Optional

from apps.voice.providers.base import (
    BaseSTTProvider,
    BaseTTSProvider,
    BaseVADProvider,
)
from apps.voice.providers.streaming_adapters import (
    StreamingSTTProvider,
    StreamingTTSProvider,
    StreamingVADProvider,
)
from core.clients.speech_override import SpeechOverride
from core.clients.voice_resolver import (
    get_stt_client,
    get_tts_client,
    get_vad_client,
)
from core.container.base import BaseContainer, lazy
from core.logging import get_logger


logger = get_logger(__name__)


class VoiceContainer(BaseContainer):
    """DI-контейнер voice сервиса.

    `create_*_provider(*, company_id, override)` — единственный способ
    получить streaming-провайдеры для одной voice сессии. Внутри они
    дёргают `voice_resolver` и оборачивают batch-клиента в адаптер.
    """

    @lazy
    def settings(self):
        from apps.voice.config import get_voice_settings

        return get_voice_settings()

    async def create_vad_provider(
        self,
        *,
        company_id: str,
        override: Optional[SpeechOverride] = None,
    ) -> BaseVADProvider:
        vad_client = await get_vad_client(company_id=company_id, override=override)
        cfg = self.settings.voice.vad
        return StreamingVADProvider(
            vad_client=vad_client,
            sample_rate=cfg.default_sample_rate,
            threshold=cfg.default_threshold,
        )

    async def create_stt_provider(
        self,
        *,
        company_id: str,
        override: Optional[SpeechOverride] = None,
    ) -> BaseSTTProvider:
        stt_client = await get_stt_client(company_id=company_id, override=override)
        cfg = self.settings.voice.stt
        return StreamingSTTProvider(
            stt_client=stt_client,
            sample_rate=16000,
            language=cfg.default_language,
        )

    async def create_tts_provider(
        self,
        *,
        company_id: str,
        override: Optional[SpeechOverride] = None,
    ) -> BaseTTSProvider:
        tts_client = await get_tts_client(company_id=company_id, override=override)
        return StreamingTTSProvider(tts_client=tts_client)


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
