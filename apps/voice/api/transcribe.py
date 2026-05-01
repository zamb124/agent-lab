"""Batch-транскрипция аудиофайла через voice service."""

from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel

from core.clients.stt_client import STTClientFactory
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
        "из CRM и других сервисов платформы."
    ),
)
async def transcribe_audio(file: UploadFile) -> TranscribeResponse:
    """Транскрибирует загруженный аудиофайл через платформенный STT-провайдер."""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Файл пуст.",
        )

    filename = file.filename or "audio.bin"
    content_type = file.content_type or "application/octet-stream"

    logger.info(
        "voice.transcribe.started",
        filename=filename,
        content_type=content_type,
        size_bytes=len(audio_bytes),
    )

    stt_client = STTClientFactory.create_client()
    result = await stt_client.transcribe_audio(
        audio_bytes=audio_bytes,
        file_name=filename,
        mime_type=content_type,
    )

    logger.info(
        "voice.transcribe.completed",
        provider=result.provider,
        text_length=len(result.text),
    )

    return TranscribeResponse(text=result.text, provider=result.provider)
