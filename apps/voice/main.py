"""FastAPI entrypoint для voice сервиса."""

from apps.voice.api.company_pronunciation_rules import router as company_pronunciation_rules_router
from apps.voice.api.company_voice_providers import router as company_voice_providers_router
from apps.voice.api.health import health_router
from apps.voice.api.platform_pronunciation_rules import (
    router as platform_pronunciation_rules_router,
)
from apps.voice.api.session import router as voice_session_router
from apps.voice.api.synthesize import synthesize_router
from apps.voice.api.transcribe import transcribe_router
from apps.voice.api.voice_providers_catalog import router as voice_providers_catalog_router
from apps.voice.config import VoiceServiceSettings, get_voice_settings
from apps.voice.di import VoiceDi
from core.app.factory import create_service_app
from core.di import recipe
from core.logging import get_logger

logger = get_logger(__name__)


async def log_voice_startup(settings: VoiceServiceSettings) -> None:
    """Deployment-default провайдеры речи на старте процесса."""
    logger.info(
        "voice.service.startup.stt.tts",
        stt=settings.voice.stt.provider,
        tts=settings.voice.tts.provider,
        vad=settings.voice.vad.provider,
    )


app = create_service_app(
    "voice",
    VoiceServiceSettings,
    VoiceDi,
    database="shared_url",
    lifecycle=(recipe(log_voice_startup),),
    pages_routers=[
        health_router,
        voice_session_router,
        transcribe_router,
        synthesize_router,
        company_voice_providers_router,
        company_pronunciation_rules_router,
        platform_pronunciation_rules_router,
        voice_providers_catalog_router,
    ],
    cors_origins=["*"],
    title="Platform Voice Gateway",
    description="Акустический шлюз: STT/TTS, VAD, barge-in",
    version="1.0.0",
    api_version="v1",
    documentation_gateway_prefix="voice",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("voice", "apps.voice.main:app", get_voice_settings())
