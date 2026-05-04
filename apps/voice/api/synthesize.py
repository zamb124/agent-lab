"""HTTP TTS endpoint — batch с Transfer-Encoding: chunked.

``POST /voice/api/v1/synthesize`` — синтезировать ``text`` в аудио-поток
через платформенного TTS-провайдера (``core.clients.voice_resolver``).
Ответ возвращается чанками (первый кусок уходит сразу после первой
синтаксической границы — правило «ни миллисекунды»), ``Content-Type``
берётся из текущего провайдера (``BaseTTSStreamer.mime_type``).

После успеха — запись ``record_tts_usage`` (если request-scope содержит
``user``); пустого текста и отсутствия ``company_id`` в контексте
запроса не допускается (``Zero-Guess``).
"""

from __future__ import annotations

from typing import AsyncIterator, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.voice.services.voice_usage import record_tts_usage
from core.clients.speech_override import SpeechOverride
from core.clients.tts_streaming import BaseTTSStreamer
from core.clients.voice_resolver import get_tts_streamer
from core.context import get_context
from core.logging import get_logger


logger = get_logger(__name__)

synthesize_router = APIRouter(prefix="/api/v1", tags=["voice-synthesize"])


class SynthesizeRequest(BaseModel):
    """Тело запроса к ``POST /voice/api/v1/synthesize``."""

    text: str = Field(min_length=1, description="Текст для озвучивания.")
    voice: Optional[str] = Field(default=None, description="Override голоса.")
    language: Optional[str] = Field(default=None, description="Override языка.")
    response_format: Optional[str] = Field(
        default=None,
        description="Формат аудио (wav/mp3/ogg/pcm/lpcm).",
    )
    provider: Optional[str] = Field(default=None, description="Override провайдера.")
    model: Optional[str] = Field(default=None, description="Override модели.")


@synthesize_router.post(
    "/synthesize",
    summary="Синтезировать речь (streaming)",
    description=(
        "Принимает текст, возвращает аудио-поток (Transfer-Encoding: chunked). "
        "Первый чанк отправляется сразу после первой синтаксической границы, "
        "без ожидания полного ответа. Провайдер выбирается через voice_resolver "
        "(override -> per-company -> deployment-default)."
    ),
    responses={
        200: {
            "content": {
                "audio/wav": {},
                "audio/mpeg": {},
                "audio/ogg": {},
                "audio/L16": {},
            }
        },
    },
)
async def synthesize(body: SynthesizeRequest) -> StreamingResponse:
    ctx = get_context()
    company_id = ctx.active_company.company_id
    if company_id == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Активная компания не определена в контексте запроса.",
        )

    override = SpeechOverride(
        provider=body.provider,
        model=body.model,
        voice=body.voice,
        language=body.language,
        response_format=body.response_format,
    )

    tts_streamer = await get_tts_streamer(
        company_id=company_id, override=override
    )

    logger.info(
        "voice.synthesize.started",
        company_id=company_id,
        provider=tts_streamer.provider,
        text_length=len(body.text),
        response_format=body.response_format,
    )

    audio_iter = _synthesize_audio_chunks(
        tts_streamer=tts_streamer, text=body.text
    )

    return StreamingResponse(
        _record_usage_after_stream(
            audio_iter=audio_iter,
            tts_streamer=tts_streamer,
            company_id=company_id,
            text=body.text,
        ),
        media_type=tts_streamer.mime_type,
        headers={"X-Voice-Provider": tts_streamer.provider},
    )


async def _single_text_stream(text: str) -> AsyncIterator[str]:
    """Одноразовый async iterator с одним text-чанком."""
    yield text


async def _synthesize_audio_chunks(
    *,
    tts_streamer: BaseTTSStreamer,
    text: str,
) -> AsyncIterator[bytes]:
    """Пропустить ``text`` через ``BaseTTSStreamer.astream`` по кускам."""
    async for audio_bytes in tts_streamer.astream(_single_text_stream(text)):
        if audio_bytes:
            yield audio_bytes


async def _record_usage_after_stream(
    *,
    audio_iter: AsyncIterator[bytes],
    tts_streamer: BaseTTSStreamer,
    company_id: str,
    text: str,
) -> AsyncIterator[bytes]:
    """Пробросить аудио-чанки клиенту и записать usage после завершения.

    Usage пишется **один раз** в конце (по полному ``len(text)``); если
    клиент отключился до конца — запись всё равно делается для того, что
    было синтезировано. При ошибке в TTS — исключение всплывает и usage
    не пишется.
    """
    total_bytes = 0
    try:
        async for chunk in audio_iter:
            total_bytes += len(chunk)
            yield chunk
    finally:
        try:
            await tts_streamer.close()
        except Exception:
            logger.warning(
                "voice.synthesize.tts_streamer_close_failed",
                company_id=company_id,
            )

        ctx = get_context()
        user = ctx.user
        if user is None:
            logger.info(
                "voice.synthesize.usage_skipped_no_user",
                company_id=company_id,
                provider=tts_streamer.provider,
                char_count=len(text),
                total_audio_bytes=total_bytes,
            )
        else:
            await record_tts_usage(
                user=user,
                company=ctx.active_company,
                provider=tts_streamer.provider,
                char_count=len(text),
                metadata={
                    "endpoint": "voice.synthesize",
                    "total_audio_bytes": total_bytes,
                },
            )
            logger.info(
                "voice.synthesize.completed",
                company_id=company_id,
                provider=tts_streamer.provider,
                char_count=len(text),
                total_audio_bytes=total_bytes,
            )


__all__ = ["synthesize_router", "SynthesizeRequest"]
