"""Health endpoint voice-сервиса.

Возвращает быстрый snapshot deployment-default провайдеров речи. Реальные
клиенты создаются per-session через ``voice_resolver``, поэтому
«готовность» в смысле HTTP-стартапа сводится к наличию валидной
конфигурации в ``settings.voice`` — контейнер считает её зарезолвленной,
если ``.settings`` успешно построился.
"""

from datetime import UTC, datetime

from fastapi import APIRouter

from apps.voice.container import get_voice_container

health_router = APIRouter(prefix="/health", tags=["voice"])


@health_router.get(
    "/providers",
    summary="Deployment-default STT/TTS/VAD провайдеры",
)
async def health_providers() -> dict:
    container = get_voice_container()

    cfg_status = "ready"
    stt_provider = ""
    tts_provider = ""
    vad_provider = ""
    try:
        settings = container.settings
        stt_provider = settings.voice.stt.provider
        tts_provider = settings.voice.tts.provider
        vad_provider = settings.voice.vad.provider
    except Exception:
        cfg_status = "not_configured"

    return {
        "status": cfg_status,
        "vad": "ready" if cfg_status == "ready" else cfg_status,
        "stt_provider": stt_provider,
        "tts_provider": tts_provider,
        "vad_provider": vad_provider,
        "checked_at": datetime.now(UTC).isoformat(),
    }
