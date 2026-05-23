"""HTTP TTS endpoint — batch с Transfer-Encoding: chunked.

``POST /voice/api/v1/synthesize`` — синтезировать ``text`` в аудио-поток
через платформенного TTS-провайдера (``core.clients.voice_resolver``).
Для ``audio/wav`` внутри собирается один RIFF: потоковый TTS режет текст на
фразы и каждая даёт **отдельный** WAV; сыря конкатенация байт ломает
``<audio>`` в браузере (слышна только первая фраза). Для иных MIME чанки
пробрасываются как раньше. ``Content-Type`` — ``BaseTTSStreamer.mime_type``.

После успеха — запись ``record_tts_usage`` (если request-scope содержит
``user``); пустого текста и отсутствия ``company_id`` в контексте
запроса не допускается (``Zero-Guess``). Если TTS не вернул ни одного
ненулевого чанка — ``502`` и лог ``voice.synthesize.empty_audio_body``.
HTTP ``4xx`` от ``provider_litserve`` (``TTSLitserveHttpError``) пробрасываются
клиенту с тем же кодом и ``detail``; ответы ``5xx`` апстрима — ``502``.
Сетевые сбои до HTTP-ответа апстрима (``httpx.RequestError``, в т.ч. нет TCP) —
``503`` с пояснением, не ``500``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.voice.services.voice_usage import record_tts_usage
from core.clients.speech_override import (
    SpeechOverride,
    SpeechProviderName,
    SpeechResponseFormat,
)
from core.clients.tts_client import TTSLitserveHttpError
from core.clients.tts_streaming import BaseTTSStreamer
from core.clients.voice_resolver import get_tts_streamer
from core.context import require_context
from core.files.media.wav_merge import merge_wav_s16le_mono_files
from core.logging import get_logger

logger = get_logger(__name__)

synthesize_router = APIRouter(prefix="/api/v1", tags=["voice-synthesize"])


def _http_status_for_litserve_tts_error(exc: TTSLitserveHttpError) -> int:
    if 400 <= exc.status_code < 500:
        return exc.status_code
    return status.HTTP_502_BAD_GATEWAY


class SynthesizeRequest(BaseModel):
    """Тело запроса к ``POST /voice/api/v1/synthesize``."""

    text: str = Field(min_length=1, description="Текст для озвучивания.")
    voice: str | None = Field(default=None, description="Override голоса.")
    language: str | None = Field(default=None, description="Override языка.")
    response_format: SpeechResponseFormat | None = Field(
        default=None,
        description="Формат аудио (wav/mp3/ogg/pcm/lpcm).",
    )
    provider: SpeechProviderName | None = Field(default=None, description="Override провайдера.")
    model: str | None = Field(default=None, description="Override модели.")


@synthesize_router.post(
    "/synthesize",
    summary="Синтезировать речь (streaming)",
    description=(
        "Принимает текст, возвращает аудио-поток. Для WAV — один корректный контейнер "
        "после полного синтеза (склейка PCM из фразовых WAV). Провайдер — voice_resolver "
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
    ctx = require_context()
    company = ctx.active_company
    if company is None or company.company_id == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Активная компания не определена в контексте запроса.",
        )
    company_id = company.company_id

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

    recorded_iter = _record_usage_after_stream(
        audio_iter=audio_iter,
        tts_streamer=tts_streamer,
        company_id=company_id,
        text=body.text,
    )

    body_iter = recorded_iter.__aiter__()
    try:
        first_chunk = await body_iter.__anext__()
    except TTSLitserveHttpError as exc:
        code = _http_status_for_litserve_tts_error(exc)
        logger.warning(
            "voice.synthesize.litserve_http_error",
            company_id=company_id,
            provider=tts_streamer.provider,
            upstream_status=exc.status_code,
            response_status=code,
        )
        raise HTTPException(status_code=code, detail=exc.detail) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "voice.synthesize.tts_upstream_unreachable",
            company_id=company_id,
            provider=tts_streamer.provider,
            error_type=type(exc).__name__,
            message=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "TTS-провайдер недоступен: нет соединения с сервисом синтеза. "
                "Проверьте, что провайдер запущен и в конфигурации voice.tts "
                "(например litserve base_url) указан верный адрес."
            ),
        ) from exc
    except StopAsyncIteration:
        logger.warning(
            "voice.synthesize.empty_audio_body",
            company_id=company_id,
            provider=tts_streamer.provider,
            char_count=len(body.text),
            total_audio_bytes=0,
            response_format=body.response_format,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "TTS вернул 0 байт аудио; провайдер см. заголовок X-Voice-Provider "
                "и лог voice.synthesize.empty_audio_body по request_id."
            ),
        )

    async def stream_from_first_chunk() -> AsyncIterator[bytes]:
        yield first_chunk
        try:
            while True:
                chunk = await body_iter.__anext__()
                yield chunk
        except StopAsyncIteration:
            return

    return StreamingResponse(
        stream_from_first_chunk(),
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
    """Собрать чанки ``astream``; для WAV — один RIFF, иначе проброс по частям."""
    raw_chunks: list[bytes] = []
    async for audio_bytes in tts_streamer.astream(_single_text_stream(text)):
        if audio_bytes:
            raw_chunks.append(audio_bytes)
    if not raw_chunks:
        return
    mime = (tts_streamer.mime_type or "").strip().lower()
    use_wav_merge = mime in ("audio/wav", "audio/wave", "audio/x-wav") or (
        len(raw_chunks[0]) >= 12
        and raw_chunks[0][:4] == b"RIFF"
        and raw_chunks[0][8:12] == b"WAVE"
    )
    if use_wav_merge:
        yield merge_wav_s16le_mono_files(raw_chunks)
        return
    for part in raw_chunks:
        yield part


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

        ctx = require_context()
        user = ctx.user
        company = ctx.active_company
        if company is None:
            raise RuntimeError("voice.synthesize usage requires active company in context")
        await record_tts_usage(
            user=user,
            company=company,
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
