"""FastAPI entrypoint для voice сервиса."""

from fastapi import FastAPI

from apps.voice.api.health import health_router
from apps.voice.api.session import router as voice_session_router
from apps.voice.api.transcribe import transcribe_router
from apps.voice.config import VoiceServiceSettings, get_voice_settings
from apps.voice.container import get_voice_container
from core.app import create_service_app
from core.logging import get_logger

logger = get_logger(__name__)


async def on_startup(app: FastAPI, container, settings: VoiceServiceSettings) -> None:
    """Инициализация voice-сервиса при старте.

    Streaming-провайдеры создаются per-session через voice_resolver.
    Здесь — только инициализация контейнера и логирование.
    """
    logger.info(
        "voice service startup: stt=%s tts=%s vad=%s",
        settings.voice.stt.provider,
        settings.voice.tts.provider,
        settings.voice.vad.provider,
    )


app = create_service_app(
    service_name="voice",
    settings_class=VoiceServiceSettings,
    get_container=get_voice_container,
    pages_routers=[health_router, voice_session_router, transcribe_router],
    repository_names=[],
    on_startup=on_startup,
    cors_origins=["*"],
    title="Platform Voice Gateway",
    description="Акустический шлюз: STT/TTS, VAD, barge-in",
    version="1.0.0",
    api_version="v1",
    include_crud_routers=False,
    documentation_gateway_prefix="voice",
)


if __name__ == "__main__":
    import uvicorn

    settings = get_voice_settings()
    uvicorn.run(
        "apps.voice.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
