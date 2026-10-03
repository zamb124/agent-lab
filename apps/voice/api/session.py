"""WebSocket-эндпоинт voice-сессии — универсальный media gateway.

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
from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from apps.voice.di import Di, VoiceDi
from apps.voice.services.speak_worker import run_speak_worker
from apps.voice.services.voice_barge_in import BargeInController
from apps.voice.services.voice_client_channel import VoiceClientChannel
from apps.voice.services.voice_session import VoiceSession
from apps.voice.workers.stt_worker import VadCallbackState, run_stt_worker
from apps.voice.workers.ws_receiver import run_ws_receiver
from core.ai.runtime import create_voice_tts_streamer
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.billing import get_billing_service
from core.billing.exceptions import BillingBalanceBlockedError
from core.billing.service import BALANCE_BLOCK_OPERATION_SPEECH
from core.billing.speech_usage import require_speech_billing_subjects
from core.clients.speech_override import (
    SpeechOverride,
    SpeechOverrideProviderName,
    SpeechProviderName,
)
from core.clients.speech_provider_catalog import STT_TTS_PROVIDER_IDS, VAD_PROVIDER_IDS
from core.context import get_context, reset_context, set_context
from core.di.boundary import require_di
from core.logging import get_logger
from core.models.context_models import Context
from core.models.identity_models import Company, User
from core.utils.background import run_with_log_context
from core.utils.tokens import get_token_service

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/ws/session",
    tags=["voice-websocket"],
)

_HEARTBEAT_INTERVAL_S = 30.0


async def _require_company_view_when_user_context(
    di: Di,
    *,
    company_id: str,
) -> None:
    context = get_context()
    if context is None or context.active_company is None:
        return
    await di.authz_service.require_can_view(AuthzObject.company(company_id))


def _speech_provider_name(value: str | None) -> SpeechProviderName | None:
    if value is None:
        return None
    for provider in STT_TTS_PROVIDER_IDS:
        if provider == value:
            return provider
    raise ValueError(f"Unsupported speech provider: {value!r}")


def _speech_override_provider_name(value: str | None) -> SpeechOverrideProviderName | None:
    if value is None:
        return None
    for provider in VAD_PROVIDER_IDS:
        if provider == value:
            return provider
    raise ValueError(f"Unsupported VAD provider: {value!r}")


async def _open_voice_session_context(websocket: WebSocket, company_id: str) -> Context:
    """Контекст голосовой сессии берётся из cookie ``auth_token``, не из потока клиента."""
    auth_token = websocket.cookies.get("auth_token")
    if not auth_token:
        raise ValueError("voice session requires auth_token cookie")
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None or token_data.user_id == "":
        raise ValueError("voice session auth_token is invalid")
    if token_data.company_id != company_id:
        raise ValueError("voice session company does not match auth_token")
    user = await User.get(token_data.user_id)
    if user is None:
        raise ValueError("voice session user is not found")
    company = await Company.get(company_id)
    if company is None:
        raise ValueError("voice session company is not found")
    return Context(
        user=user,
        active_company=company,
        session_id=token_data.session_id,
        channel="voice",
        auth_token=auth_token,
    )


@router.websocket("/{session_id}")
async def voice_session(
    websocket: WebSocket,
    session_id: str,
    company_id: Annotated[
        str,
        Query(description="ID компании, в контексте которой работает сессия."),
    ],
    stt_provider_name: Annotated[
        str | None,
        Query(description="Override STT провайдера для сессии."),
    ] = None,
    stt_model: Annotated[
        str | None,
        Query(description="Override STT модели."),
    ] = None,
    tts_provider_name: Annotated[
        str | None,
        Query(description="Override TTS провайдера."),
    ] = None,
    tts_model: Annotated[
        str | None,
        Query(description="Override TTS модели."),
    ] = None,
    tts_voice: Annotated[
        str | None,
        Query(description="Override TTS голоса."),
    ] = None,
    tts_sample_rate: Annotated[
        int | None,
        Query(description="Override частоты дискретизации TTS (Гц)."),
    ] = None,
    vad_provider_name: Annotated[
        str | None,
        Query(description="Override VAD провайдера."),
    ] = None,
    vad_sample_rate: Annotated[
        int | None,
        Query(description="Override частоты дискретизации VAD (Гц)."),
    ] = None,
    vad_threshold: Annotated[
        float | None,
        Query(description="Override порога детекции VAD [0..1]."),
    ] = None,
    language: Annotated[
        str | None,
        Query(
            description=(
                "Язык сессии (ISO 639-1): STT и выбор TTS-модели платформенного voice-провайдера "
                "по `synthesis_locale` в каталоге."
            ),
        ),
    ] = None,
) -> None:
    """WebSocket сессия: PCM uplink + text/PCM downlink.

    Параметры провайдеров опционально перекрываются query (per-call
    ``SpeechOverride``); иначе берутся per-company overrides или
    deployment-default из ``settings.voice.<kind>``.
    """
    if company_id == "":
        await websocket.close(code=1008)
        return

    try:
        session_context = await _open_voice_session_context(websocket, company_id)
    except ValueError as exc:
        logger.info(
            "voice.session.auth_rejected",
            session_id=session_id,
            company_id=company_id,
            reason=str(exc),
        )
        await websocket.close(code=1008, reason="company context required")
        return

    context_token = set_context(session_context)
    di = require_di(websocket, VoiceDi)

    tts_voice_q: str | None
    if isinstance(tts_voice, str):
        stripped = tts_voice.strip()
        tts_voice_q = stripped if stripped != "" else None
    else:
        tts_voice_q = None

    await websocket.accept()
    try:
        await _require_company_view_when_user_context(di, company_id=company_id)
    except AuthzDenied:
        await websocket.close(code=1008, reason="permission denied")
        return

    try:
        user, company = require_speech_billing_subjects()
        await get_billing_service().require_balance_for_billable_operation(
            company.company_id,
            str(user.user_id).strip(),
            operation_code=BALANCE_BLOCK_OPERATION_SPEECH,
            notification_service="voice",
        )
    except BillingBalanceBlockedError:
        await websocket.close(code=1008, reason="billing_balance_blocked")
        return
    except ValueError:
        await websocket.close(code=1008, reason="company context required")
        return

    logger.info(
        "voice.session.connected",
        session_id=session_id,
        company_id=company_id,
    )

    session = VoiceSession(session_id=session_id)
    channel = VoiceClientChannel(websocket, session_id=session_id)

    try:
        stt_provider = _speech_provider_name(stt_provider_name)
        tts_provider = _speech_provider_name(tts_provider_name)
        vad_provider_name_resolved = _speech_override_provider_name(vad_provider_name)
    except ValueError:
        await websocket.close(code=1008)
        return

    stt_override = SpeechOverride(
        provider=stt_provider,
        model=stt_model,
        language=language,
    )
    tts_override = SpeechOverride(
        provider=tts_provider,
        model=tts_model,
        voice=tts_voice_q,
        language=language,
        sample_rate=tts_sample_rate,
    )
    vad_override = SpeechOverride(
        provider=vad_provider_name_resolved,
        sample_rate=vad_sample_rate,
        threshold=vad_threshold,
    )

    try:
        vad_provider = await di.session_providers.create_vad_provider(
            company_id=company_id, override=vad_override
        )
        stt_provider = await di.session_providers.create_stt_provider(
            company_id=company_id, override=stt_override
        )
        tts_streamer = await create_voice_tts_streamer(
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
            mime_type=tts_streamer.content_type,
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

    settings = di.session_providers.settings
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

    async def _on_vad_state(_sess: VoiceSession, state: VadCallbackState) -> None:
        await channel.send_vad(state)

    all_tasks: list[asyncio.Task[None]] = []

    def _spawn(coro: Awaitable[None], task_name: str) -> None:
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
        reset_context(context_token)
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
