"""Health endpoint voice-сервиса.

Возвращает быстрый snapshot deployment-default провайдеров речи. Реальные
клиенты создаются per-session через ``voice_resolver``, поэтому
«готовность» в смысле HTTP-стартапа сводится к наличию валидной
конфигурации в ``settings.voice`` — контейнер считает её зарезолвленной,
если ``.settings`` успешно построился.
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from apps.voice.dependencies import ContainerDep
from apps.voice.models import VoiceProvidersHealth

health_router = APIRouter(prefix="/health", tags=["voice"])


@health_router.get(
    "/providers",
    summary="Deployment-default STT/TTS/VAD провайдеры",
    response_model=VoiceProvidersHealth,
)
async def health_providers(container: ContainerDep) -> VoiceProvidersHealth:
    settings = container.settings
    return VoiceProvidersHealth(
        status="ready",
        vad="ready",
        stt_provider=settings.voice.stt.provider,
        tts_provider=settings.voice.tts.provider,
        vad_provider=settings.voice.vad.provider,
        checked_at=datetime.now(UTC),
    )
