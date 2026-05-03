"""WebSocket session endpoint для voice-сервиса."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from apps.voice.container import get_voice_container
from apps.voice.services.llm_bridge import run_llm_bridge
from apps.voice.services.voice_barge_in import BargeInController
from apps.voice.services.voice_chunker import VoiceChunker
from apps.voice.services.voice_session import VoiceSession
from apps.voice.workers.audio_receiver import run_audio_receiver
from apps.voice.workers.audio_sender import run_audio_sender
from apps.voice.workers.stt_worker import run_stt_worker
from apps.voice.workers.tts_worker import run_tts_worker
from core.clients.speech_override import SpeechOverride
from core.logging import get_logger
from core.utils.background import run_with_log_context

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/ws/session",
    tags=["voice-websocket"],
)


@router.websocket("/{session_id}")
async def voice_session(
    websocket: WebSocket,
    session_id: str,
    company_id: str = Query(..., description="ID компании, в контексте которой работает сессия."),
    stt_provider_name: str | None = Query(default=None, description="Override STT провайдера для сессии."),
    stt_model: str | None = Query(default=None, description="Override STT модели."),
    tts_provider_name: str | None = Query(default=None, description="Override TTS провайдера."),
    tts_model: str | None = Query(default=None, description="Override TTS модели."),
    tts_voice: str | None = Query(default=None, description="Override TTS голоса."),
    vad_provider_name: str | None = Query(default=None, description="Override VAD провайдера."),
    language: str | None = Query(default=None, description="Override языка (для STT)."),
) -> None:
    """WebSocket соединение для голосового стрима.

    Принимает PCM 16kHz mono 16-bit, возвращает аудио от TTS. Параметры
    провайдеров можно перекрыть через query (per-call SpeechOverride);
    иначе берётся per-company настройка из `company_voice_providers` или
    deployment-default из `settings.voice.<kind>`.
    """
    if company_id == "":
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logger.info(
        "voice client connected: session_id=%s company_id=%s",
        session_id,
        company_id,
    )

    container = get_voice_container()
    session = VoiceSession(session_id=session_id)

    stt_override = SpeechOverride(
        provider=stt_provider_name,
        model=stt_model,
        language=language,
    )
    tts_override = SpeechOverride(
        provider=tts_provider_name,
        model=tts_model,
        voice=tts_voice,
    )
    vad_override = SpeechOverride(provider=vad_provider_name)

    try:
        vad_provider = await container.create_vad_provider(
            company_id=company_id, override=vad_override
        )
        stt_provider = await container.create_stt_provider(
            company_id=company_id, override=stt_override
        )
        tts_provider = await container.create_tts_provider(
            company_id=company_id, override=tts_override
        )
    except Exception:
        logger.exception(
            "voice provider resolve failed: session_id=%s company_id=%s",
            session_id,
            company_id,
        )
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "voice/provider/resolve_failed",
                    "detail": "Speech provider resolution failed.",
                }
            )
        finally:
            await websocket.close(code=1011)
        return

    try:
        await stt_provider.init()
        await tts_provider.init()
    except Exception:
        logger.exception(
            "voice provider init failed: session_id=%s, closing session", session_id
        )
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "voice/provider/init_failed",
                    "detail": "STT or TTS provider failed to initialize.",
                }
            )
        finally:
            await websocket.close(code=1011)
        return

    chunker = VoiceChunker()
    settings = container.settings
    barge_in = BargeInController(
        enabled=settings.barge_in.enabled,
        smart_turn_buffer_ms=settings.barge_in.smart_turn_buffer_ms,
        command_words=list(settings.barge_in.smart_turn_command_words),
        flush_timeout_ms=settings.barge_in.flush_timeout_ms,
        cooldown_ms=settings.barge_in.cooldown_ms,
    )

    async def _on_full_transcription(sess: VoiceSession, text: str) -> None:
        logger.info(
            "voice/transcription/completed: session_id=%s text=%s",
            sess.session_id,
            text,
        )

    async def _on_error(sess: VoiceSession, code: str, detail: str) -> None:
        try:
            await websocket.send_json({"type": "error", "code": code, "detail": detail})
        except Exception:
            pass

    async def send_heartbeat(sess: VoiceSession, ws: WebSocket) -> None:
        """Периодически шлёт пинг для удержания соединения."""
        while sess.active:
            try:
                await asyncio.sleep(30)
                if not sess.active:
                    break
                await ws.send_json({"type": "ping"})
            except asyncio.CancelledError:
                raise
            except Exception:
                break

    try:
        all_tasks: list[asyncio.Task[Any]] = []

        def _spawn(coro: Awaitable[Any], task_name: str) -> None:
            task = run_with_log_context(coro, name=task_name)
            all_tasks.append(task)
            session.add_task(task)

        _spawn(run_audio_receiver(session, websocket), f"voice.audio_receiver.{session_id}")
        _spawn(
            run_stt_worker(
                session, vad_provider, stt_provider,
                on_full_transcription=_on_full_transcription,
                barge_in=barge_in,
            ),
            f"voice.stt_worker.{session_id}",
        )
        _spawn(run_llm_bridge(session), f"voice.llm_bridge.{session_id}")
        _spawn(
            run_tts_worker(session, tts_provider, chunker),
            f"voice.tts_worker.{session_id}",
        )
        _spawn(run_audio_sender(session, websocket), f"voice.audio_sender.{session_id}")
        _spawn(send_heartbeat(session, websocket), f"voice.heartbeat.{session_id}")

        await asyncio.gather(*all_tasks, return_exceptions=True)

    except WebSocketDisconnect:
        logger.info("voice client disconnected: session_id=%s", session_id)
    except Exception:
        logger.exception("voice session error: session_id=%s", session_id)
    finally:
        await session.cancel()
        logger.info("voice session cleanup done: session_id=%s", session_id)
