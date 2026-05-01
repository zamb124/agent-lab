"""Health endpoint для voice сервиса."""

from datetime import UTC, datetime

from fastapi import APIRouter

from apps.voice.container import get_voice_container

health_router = APIRouter(prefix="/health", tags=["voice"])


@health_router.get(
    "/providers",
    summary="Статус провайдеров voice",
)
async def health_providers() -> dict:
    """Проверка работоспособности голосовых компонентов."""
    container = get_voice_container()

    vad_status = "ready"
    try:
        _ = container.vad_provider
    except Exception:
        vad_status = "not_loaded"

    return {
        "vad": vad_status,
        "checked_at": datetime.now(UTC).isoformat(),
    }
