"""Health-эндпоинт voice-сервиса.

Возвращает быстрый snapshot deployment-default провайдеров речи. Реальные
клиенты создаются per-session через ``voice_resolver``, поэтому
«готовность» в смысле HTTP-стартапа сводится к наличию валидной
конфигурации в ``settings.voice`` — процесс считает её зарезолвленной,
если ``.settings`` успешно построился.
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from apps.voice.di import Di
from apps.voice.models import VoiceProvidersHealth

health_router = APIRouter(prefix="/health", tags=["voice"])


@health_router.get(
    "/providers",
    summary="Deployment-default STT/TTS/VAD провайдеры",
    response_model=VoiceProvidersHealth,
)
async def health_providers(di: Di) -> VoiceProvidersHealth:
    settings = di.session_providers.settings
    return VoiceProvidersHealth(
        status="ready",
        vad="ready",
        stt_provider=settings.voice.stt.provider,
        tts_provider=settings.voice.tts.provider,
        vad_provider=settings.voice.vad.provider,
        checked_at=datetime.now(UTC),
    )
