"""Health endpoint voice-сервиса.

Возвращает быстрый snapshot deployment-default провайдеров речи. Реальные
клиенты создаются per-session через ``voice_resolver``, поэтому
«готовность» в смысле HTTP-стартапа сводится к наличию валидной
конфигурации в ``settings.voice`` — контейнер считает её зарезолвленной,
если ``.settings`` успешно построился.
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from apps.voice.dependencies import ContainerDep

health_router = APIRouter(prefix="/health", tags=["voice"])


@health_router.get(
    "/providers",
    summary="Deployment-default STT/TTS/VAD провайдеры",
)
async def health_providers(container: ContainerDep) -> dict[str, Any]:
    settings = container.settings
    stt_provider = settings.voice.stt.provider
    tts_provider = settings.voice.tts.provider
    vad_provider = settings.voice.vad.provider

    return {
        "status": "ready",
        "vad": "ready",
        "stt_provider": stt_provider,
        "tts_provider": tts_provider,
        "vad_provider": vad_provider,
        "checked_at": datetime.now(UTC).isoformat(),
    }
