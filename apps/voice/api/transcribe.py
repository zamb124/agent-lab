"""Batch-транскрипция аудиофайла через voice service.

REST: POST /voice/api/v1/transcribe (audio/* multipart/form-data,
поле `file`). Batch-сценарии (sync, capabilities, файлы). UI-диктовка
идёт через VoiceMediaSession (WS), не через этот POST. Клиент
выбирается через `core.ai.runtime.transcribe_audio_bytes(*, company_id,
override)` — один и тот же tier-резолв, что и для real-time WS.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from apps.voice.dependencies import ContainerDep
from core.ai.runtime import transcribe_audio_bytes
from core.authz.models import AuthzObject
from core.billing.service import COST_ORIGIN_PLATFORM
from core.billing.speech_usage import record_stt_usage_span
from core.clients.speech_override import SpeechOverride, SpeechProviderName
from core.context import get_context, require_context
from core.files.audio_probe import probe_audio_duration_seconds_from_upload
from core.files.media.ffmpeg_wav import transcode_audio_bytes_to_wav_pcm16_mono
from core.logging import get_logger

logger = get_logger(__name__)

transcribe_router = APIRouter(prefix="/api/v1", tags=["voice-transcribe"])


async def _require_company_view_when_user_context(
    container: ContainerDep,
    *,
    company_id: str,
) -> None:
    context = get_context()
    if context is None or context.active_company is None:
        return
    await container.authz_service.require_can_view(AuthzObject.company(company_id))


class TranscribeResponse(BaseModel):
    text: str
    provider: str


@transcribe_router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    summary="Транскрибировать аудиофайл",
    description=(
        "Принимает аудиофайл (multipart/form-data, поле `file`), "
        "нормализует в WAV 16 kHz mono и возвращает распознанный текст. "
        "Только batch (sync, capabilities, файлы). UI-диктовка идёт через "
        "VoiceMediaSession (WS), не через этот POST. Выбор провайдера — через "
        "core.ai.runtime (tier-резолв override -> per-company -> deployment-default)."
    ),
)
async def transcribe_audio(
    container: ContainerDep,
    file: UploadFile,
    provider: Annotated[SpeechProviderName | None, Form()] = None,
    model: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
) -> TranscribeResponse:
    """Транскрибирует загруженный аудиофайл через платформенный STT-провайдер."""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File is empty.",
        )

    filename = file.filename or "audio.bin"
    content_type = file.content_type or "application/octet-stream"

    ctx = require_context()
    company = ctx.active_company
    if company is None or company.company_id == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Active company is not set in the request context.",
        )
    company_id = company.company_id

    await _require_company_view_when_user_context(container, company_id=company_id)

    override = SpeechOverride(provider=provider, model=model, language=language)

    logger.info(
        "voice.transcribe.started",
        filename=filename,
        content_type=content_type,
        size_bytes=len(audio_bytes),
        company_id=company_id,
    )

    try:
        wav_bytes = transcode_audio_bytes_to_wav_pcm16_mono(
            audio_bytes=audio_bytes,
            file_name=filename,
            content_type=content_type,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    wav_file_name = "voice-input.wav"
    wav_content_type = "audio/wav"

    result = await transcribe_audio_bytes(
        company_id=company_id,
        audio_bytes=wav_bytes,
        file_name=wav_file_name,
        content_type=wav_content_type,
        override=override,
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
            data=wav_bytes, file_name=wav_file_name
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
        await record_stt_usage_span(
            user=ctx.user,
            company=company,
            provider=result.provider,
            audio_seconds=audio_seconds,
            cost_origin=COST_ORIGIN_PLATFORM,
            extra_attributes={
                "endpoint": "voice.transcribe",
                "size_bytes": len(audio_bytes),
            },
        )

    return TranscribeResponse(text=result.text, provider=result.provider)
