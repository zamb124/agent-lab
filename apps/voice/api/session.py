"""WebSocket endpoint voice-сессии — универсальный media gateway.

Сервис ``apps/voice`` **не знает** про ``apps/flows``, A2A и агентскую
логику. Он принимает аудио с клиента, делает STT/VAD, по команде клиента
синтезирует речь (TTS) и отправляет события пережёвывания через
``VoiceClientChannel``. Связку с логикой агента делает клиент (веб-JS
``core/frontend/static/lib/voice/voice-agent-bridge.js`` или нативный
bridge мобильного приложения).

Контракт WS-фреймов — см. ``.cursor/rules/voice.mdc`` и
``apps/voice/services/voice_client_channel.py``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from apps.voice.container import get_voice_container
from apps.voice.services.speak_worker import run_speak_worker
from apps.voice.services.voice_barge_in import BargeInController
from apps.voice.services.voice_client_channel import VoiceClientChannel
from apps.voice.services.voice_session import VoiceSession
from apps.voice.workers.stt_worker import run_stt_worker
from apps.voice.workers.ws_receiver import run_ws_receiver
from core.clients.speech_override import SpeechOverride
from core.clients.voice_resolver import get_tts_streamer
from core.logging import get_logger
from core.utils.background import run_with_log_context


logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/ws/session",
    tags=["voice-websocket"],
)

_HEARTBEAT_INTERVAL_S = 30.0


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
    tts_sample_rate: int | None = Query(default=None, description="Override частоты дискретизации TTS (Гц)."),
    vad_provider_name: str | None = Query(default=None, description="Override VAD провайдера."),
    vad_sample_rate: int | None = Query(default=None, description="Override частоты дискретизации VAD (Гц)."),
    vad_threshold: float | None = Query(default=None, description="Override порога детекции VAD [0..1]."),
    language: str | None = Query(default=None, description="Язык сессии (ISO 639-1): STT и выбор TTS-модели LitServe по `synthesis_locale` в каталоге."),
) -> None:
    """WebSocket сессия: PCM uplink + text/PCM downlink.

    Параметры провайдеров опционально перекрываются query (per-call
    ``SpeechOverride``); иначе берутся per-company overrides или
    deployment-default из ``settings.voice.<kind>``.
    """
    if company_id == "":
        await websocket.close(code=1008)
        return

    tts_voice_q: str | None
    if isinstance(tts_voice, str):
        stripped = tts_voice.strip()
        tts_voice_q = stripped if stripped != "" else None
    else:
        tts_voice_q = None

    await websocket.accept()
    logger.info(
        "voice.session.connected",
        session_id=session_id,
        company_id=company_id,
    )

    container = get_voice_container()
    session = VoiceSession(session_id=session_id)
    channel = VoiceClientChannel(websocket, session_id=session_id)

    stt_override = SpeechOverride(
        provider=stt_provider_name,
        model=stt_model,
        language=language,
    )
    tts_override = SpeechOverride(
        provider=tts_provider_name,
        model=tts_model,
        voice=tts_voice_q,
        language=language,
        sample_rate=tts_sample_rate,
    )
    vad_override = SpeechOverride(
        provider=vad_provider_name,
        sample_rate=vad_sample_rate,
        threshold=vad_threshold,
    )

    try:
        vad_provider = await container.create_vad_provider(
            company_id=company_id, override=vad_override
        )
        stt_provider = await container.create_stt_provider(
            company_id=company_id, override=stt_override
        )
        tts_streamer = await get_tts_streamer(
            company_id=company_id, override=tts_override
        )
    except Exception as exc:
        logger.exception(
            "voice.session.provider_resolve_failed",
            session_id=session_id,
            company_id=company_id,
        )
        await channel.send_error(
            code="voice/provider/resolve_failed",
            detail=str(exc),
        )
        await websocket.close(code=1011)
        return

    try:
        await channel.send_media_config(
            mime_type=tts_streamer.mime_type,
            sample_rate=tts_streamer.sample_rate,
            channels=1,
        )
    except Exception:
        logger.exception(
            "voice.session.media_config_send_failed",
            session_id=session_id,
        )

    try:
        await stt_provider.init()
    except Exception as exc:
        logger.exception(
            "voice.session.provider_init_failed",
            session_id=session_id,
        )
        await channel.send_error(
            code="voice/provider/init_failed",
            detail=str(exc),
        )
        await websocket.close(code=1011)
        return

    settings = container.settings
    barge_in = BargeInController(
        enabled=settings.barge_in.enabled,
        smart_turn_buffer_ms=settings.barge_in.smart_turn_buffer_ms,
        command_words=list(settings.barge_in.smart_turn_command_words),
        flush_timeout_ms=settings.barge_in.flush_timeout_ms,
        cooldown_ms=settings.barge_in.cooldown_ms,
    )

    async def _on_final_transcription(
        sess: VoiceSession, text: str, lang: str | None
    ) -> None:
        logger.info(
            "voice.session.transcription_final",
            session_id=sess.session_id,
            text_length=len(text),
        )
        await channel.send_transcript(text=text, final=True, language=lang)

    async def _on_partial_transcription(
        sess: VoiceSession, text: str, lang: str | None
    ) -> None:
        logger.debug(
            "voice.session.transcription_partial",
            session_id=sess.session_id,
            text_length=len(text),
        )
        await channel.send_transcript(text=text, final=False, language=lang)

    async def _on_vad_state(sess: VoiceSession, state: str) -> None:
        if state not in ("started", "ended"):
            return
        await channel.send_vad(state)  # type: ignore[arg-type]

    all_tasks: list[asyncio.Task[Any]] = []

    def _spawn(coro: Awaitable[Any], task_name: str) -> None:
        task = run_with_log_context(
            coro, name=task_name, background_kind="voice_session"
        )
        all_tasks.append(task)
        session.add_task(task)

    try:
        _spawn(
            run_ws_receiver(session, websocket, channel),
            f"voice.ws_receiver.{session_id}",
        )
        _spawn(
            run_stt_worker(
                session,
                vad_provider,
                stt_provider,
                on_final_transcription=_on_final_transcription,
                on_partial_transcription=_on_partial_transcription,
                on_vad_state=_on_vad_state,
                barge_in=barge_in,
                language=language,
                channel=channel,
            ),
            f"voice.stt_worker.{session_id}",
        )
        _spawn(
            run_speak_worker(session, tts_streamer, channel=channel),
            f"voice.speak_worker.{session_id}",
        )
        _spawn(
            _run_heartbeat(session=session, channel=channel),
            f"voice.heartbeat.{session_id}",
        )

        # Не использовать gather без отмены: ws_receiver может завершиться при
        # disconnect клиента, тогда воркеры остаются в блокирующих get() очередей
        # навсегда — gather бы не вернулся. Ждём первого завершившегося участника,
        # затем в finally session.cancel() снимает остальные.
        done, _pending = await asyncio.wait(
            all_tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            if task.cancelled():
                continue
            exc = task.exception()
            if exc is not None:
                logger.warning(
                    "voice.session.worker_first_completed_with_error",
                    session_id=session_id,
                    worker=task.get_name(),
                    exception_type=type(exc).__name__,
                    exception_detail=str(exc),
                )
            else:
                logger.debug(
                    "voice.session.worker_first_completed_ok",
                    session_id=session_id,
                    worker=task.get_name(),
                )

    except WebSocketDisconnect:
        logger.info("voice.session.disconnected", session_id=session_id)
    except Exception:
        logger.exception("voice.session.error", session_id=session_id)
    finally:
        channel.mark_closed()
        await session.cancel()
        try:
            await tts_streamer.close()
        except Exception:
            logger.warning(
                "voice.session.tts_streamer_close_failed",
                session_id=session_id,
            )
        logger.info("voice.session.cleanup_done", session_id=session_id)


async def _run_heartbeat(
    *, session: VoiceSession, channel: VoiceClientChannel
) -> None:
    """Периодический ``{"type":"ping"}`` для удержания соединения."""
    while session.active:
        try:
            await asyncio.sleep(_HEARTBEAT_INTERVAL_S)
        except asyncio.CancelledError:
            raise
        if not session.active:
            break
        if not channel.is_open:
            break
        try:
            await channel.send_ping()
        except Exception:
            break
