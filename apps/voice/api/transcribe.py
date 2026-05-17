"""Batch-транскрипция аудиофайла через voice service.

REST-зеркало: POST /voice/api/v1/transcribe (audio/* multipart/form-data,
поле `file`). Используется CRM/Sync для batch-сценариев. Клиент
выбирается через `core.clients.voice_resolver.get_stt_client(*, company_id,
override)` — один и тот же tier-резолв, что и для real-time WS.
"""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from apps.voice.services.voice_usage import record_stt_usage
from core.clients.speech_override import SpeechOverride, SpeechProviderName
from core.clients.voice_resolver import get_stt_client
from core.context import require_context
from core.files.audio_probe import probe_audio_duration_seconds_from_upload
from core.logging import get_logger

logger = get_logger(__name__)

transcribe_router = APIRouter(prefix="/api/v1", tags=["voice-transcribe"])


class TranscribeResponse(BaseModel):
    text: str
    provider: str


@transcribe_router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    summary="Транскрибировать аудиофайл",
    description=(
        "Принимает аудиофайл (multipart/form-data, поле `file`), "
        "возвращает распознанный текст. Используется для batch-транскрипции "
        "из CRM и других сервисов платформы. Выбор провайдера — через "
        "voice_resolver (tier-резолв override -> per-company -> deployment-default)."
    ),
)
async def transcribe_audio(
    file: UploadFile,
    provider: SpeechProviderName | None = Form(default=None),
    model: str | None = Form(default=None),
    language: str | None = Form(default=None),
) -> TranscribeResponse:
    """Транскрибирует загруженный аудиофайл через платформенный STT-провайдер."""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Файл пуст.",
        )

    filename = file.filename or "audio.bin"
    content_type = file.content_type or "application/octet-stream"

    ctx = require_context()
    company = ctx.active_company
    if company is None or company.company_id == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Активная компания не определена в контексте запроса.",
        )
    company_id = company.company_id

    override = SpeechOverride(provider=provider, model=model, language=language)

    logger.info(
        "voice.transcribe.started",
        filename=filename,
        content_type=content_type,
        size_bytes=len(audio_bytes),
        company_id=company_id,
    )

    stt_client = await get_stt_client(company_id=company_id, override=override)
    result = await stt_client.transcribe_audio(
        audio_bytes=audio_bytes,
        file_name=filename,
        mime_type=content_type,
        language=language,
    )

    logger.info(
        "voice.transcribe.completed",
        provider=result.provider,
        text_length=len(result.text),
        company_id=company_id,
    )

    try:
        audio_seconds = await probe_audio_duration_seconds_from_upload(
            data=audio_bytes, file_name=filename
        )
    except ValueError as exc:
        logger.warning(
            "voice.transcribe.stt_usage_skipped",
            reason=str(exc),
            company_id=company_id,
            user_id=ctx.user.user_id,
            provider=result.provider,
            size_bytes=len(audio_bytes),
        )
    else:
        await record_stt_usage(
            user=ctx.user,
            company=company,
            provider=result.provider,
            audio_seconds=audio_seconds,
            metadata={
                "endpoint": "voice.transcribe",
                "size_bytes": len(audio_bytes),
            },
        )

    return TranscribeResponse(text=result.text, provider=result.provider)
