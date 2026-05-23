"""STT worker — PCM → VAD → STT → text; публикует media-события.

Единственный источник правды для событий распознавания в voice-сессии:

* ``on_vad_state(session, "started"|"ended")`` — смена состояния VAD
  (передний фронт речи / устойчивая пауза). Все пороги/гистерезис/
  длительности smoothing живут внутри ``StreamingVADProvider`` (см.
  `voice.mdc`); worker — машина состояний на единственном булевом
  ``is_speech``, без своих счётчиков silence/speech;
* ``on_final_transcription(session, text, language)`` — финальная фраза
  после паузы: возврат от ``stt_provider.flush_buffer()``;
* ``on_partial_transcription(session, text, language)`` — промежуточная
  транскрипция при открытом VAD-окне (chunked-batch ``peek_transcript``);
* при ``tts_is_active=True`` и срабатывании ``BargeInController`` —
  воркер сам вызывает ``execute_barge_in(session)`` со сбросом STT/VAD.

При переходе SILENCE → SPEECH worker вызывает
``vad_provider.consume_preroll()`` и пушит pre-roll PCM в STT-буфер
перед текущим фреймом — без этого первые ~150-300 мс слова теряются и
STT отдаёт огрызок (см. `voice.mdc` секция «Streaming VAD»).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from apps.voice.providers.base import BaseSTTProvider, BaseVADProvider
from apps.voice.services.voice_barge_in import BargeInController
from apps.voice.services.voice_client_channel import VoiceClientChannel
from apps.voice.services.voice_session import MicFinalizeRequest, VoiceSession
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)

OnFinalTranscription = Callable[[VoiceSession, str, str | None], Awaitable[None]] | None
OnPartialTranscription = Callable[[VoiceSession, str, str | None], Awaitable[None]] | None
OnVadState = Callable[[VoiceSession, str], Awaitable[None]] | None

_FRAME_DURATION_S = 0.02


async def _process_mic_finalize_request(
    *,
    session: VoiceSession,
    mic_req: MicFinalizeRequest,
    vad_open_before: bool,
    speech_frames_in_window: int,
    last_partial_at_frame: int,
    last_partial_preview: str,
    stt_provider: BaseSTTProvider,
    on_final_transcription: OnFinalTranscription,
    on_vad_state: OnVadState,
    channel: VoiceClientChannel | None,
    language: str | None,
) -> tuple[bool, int, int, str]:
    """Закрыть открытый сегмент речи немедленно (как пауза VAD без ожидания тишины)."""
    flush_exc: Exception | None = None
    speech_out = speech_frames_in_window
    lp_frame = last_partial_at_frame
    lp_preview = last_partial_preview

    try:
        if vad_open_before:
            speech_out = 0
            lp_frame = 0
            lp_preview = ""

            if on_vad_state is not None:
                await on_vad_state(session, "ended")

            try:
                result = await stt_provider.flush_buffer()
            except Exception as exc:
                flush_exc = exc
                logger.exception(
                    "voice.stt_worker.mic_finalize_flush_failed",
                    session_id=session.session_id,
                )
                if channel is not None and channel.is_open:
                    try:
                        await channel.send_error(
                            code="voice/stt/flush_failed",
                            detail=str(exc),
                        )
                    except Exception:
                        logger.warning(
                            "voice.stt_worker.error_notify_failed",
                            session_id=session.session_id,
                        )
            else:
                if (
                    result is not None
                    and result.text
                    and on_final_transcription is not None
                ):
                    try:
                        logger.info(
                            "voice.stt_worker.mic_finalize_transcription",
                            session_id=session.session_id,
                            text_length=len(result.text),
                        )
                        await on_final_transcription(session, result.text, language)
                    except Exception as exc:
                        flush_exc = exc
                        logger.exception(
                            "voice.stt_worker.mic_finalize_callback_failed",
                            session_id=session.session_id,
                        )
    finally:
        if channel is not None and channel.is_open:
            try:
                await channel.send_recording_finalized()
            except Exception:
                logger.warning(
                    "voice.stt_worker.finalize_done_send_failed",
                    session_id=session.session_id,
                )
        if not mic_req.complete.done():
            if flush_exc is not None:
                mic_req.complete.set_exception(flush_exc)
            else:
                mic_req.complete.set_result(None)

    return False, speech_out, lp_frame, lp_preview


async def run_stt_worker(
    session: VoiceSession,
    vad_provider: BaseVADProvider,
    stt_provider: BaseSTTProvider,
    *,
    on_final_transcription: OnFinalTranscription = None,
    on_vad_state: OnVadState = None,
    on_partial_transcription: OnPartialTranscription = None,
    barge_in: BargeInController | None = None,
    language: str | None = None,
    channel: VoiceClientChannel | None = None,
) -> None:
    """Пайплайн: audio_in_queue → VAD → STT → callbacks."""
    stt_cfg = get_settings().voice.stt
    partial_enabled = stt_cfg.partial_transcripts_enabled
    partial_step = stt_cfg.partial_min_speech_frames
    partial_min_buffer_bytes = (
        16000 * 2 * stt_cfg.partial_min_buffer_ms // 1000
    )

    vad_open: bool = False
    speech_frames_in_window: int = 0
    last_partial_at_frame: int = 0
    last_partial_preview: str = ""

    while session.active:
        try:
            raw_in = await session.audio_in_queue.get()
        except asyncio.CancelledError:
            raise

        if isinstance(raw_in, MicFinalizeRequest):
            vad_open, speech_frames_in_window, last_partial_at_frame, last_partial_preview = (
                await _process_mic_finalize_request(
                    session=session,
                    mic_req=raw_in,
                    vad_open_before=vad_open,
                    speech_frames_in_window=speech_frames_in_window,
                    last_partial_at_frame=last_partial_at_frame,
                    last_partial_preview=last_partial_preview,
                    stt_provider=stt_provider,
                    on_final_transcription=on_final_transcription,
                    on_vad_state=on_vad_state,
                    channel=channel,
                    language=language,
                )
            )
            continue

        audio_frame = raw_in
        if not isinstance(audio_frame, bytes):
            raise TypeError(
                "stt_worker: элемент audio_in_queue должен быть bytes или MicFinalizeRequest."
            )

        try:
            is_speech = await vad_provider.detect_speech(audio_frame, sample_rate=16000)
        except Exception:
            logger.warning(
                "voice.stt_worker.vad_error",
                session_id=session.session_id,
            )
            continue

        if is_speech and not vad_open:
            vad_open = True
            speech_frames_in_window = 0
            last_partial_at_frame = 0
            last_partial_preview = ""
            preroll = vad_provider.consume_preroll()
            if preroll:
                await stt_provider.push_audio(preroll)
            if on_vad_state is not None:
                await on_vad_state(session, "started")

        if is_speech:
            speech_frames_in_window += 1
            await stt_provider.push_audio(audio_frame)

            if (
                barge_in is not None
                and session.is_tts_active
                and barge_in.is_barge_in(
                    vad_speech_seconds=speech_frames_in_window * _FRAME_DURATION_S,
                    stt_preview_text=last_partial_preview,
                    tts_is_active=True,
                )
            ):
                await barge_in.execute_barge_in(
                    session,
                    stt_provider=stt_provider,
                    vad_provider=vad_provider,
                    channel=channel,
                    language=language,
                    peek_min_buffer_bytes=partial_min_buffer_bytes,
                )
                vad_open = False
                speech_frames_in_window = 0
                last_partial_at_frame = 0
                last_partial_preview = ""
                continue

            if (
                partial_enabled
                and on_partial_transcription is not None
                and speech_frames_in_window - last_partial_at_frame >= partial_step
            ):
                last_partial_at_frame = speech_frames_in_window
                try:
                    partial = await stt_provider.peek_transcript(
                        min_buffer_bytes=partial_min_buffer_bytes,
                    )
                except Exception:
                    logger.warning(
                        "voice.stt_worker.partial_failed",
                        session_id=session.session_id,
                    )
                    partial = None
                if partial is not None and partial.text:
                    last_partial_preview = partial.text.strip()
                    await on_partial_transcription(
                        session, partial.text, language
                    )
            continue

        if not is_speech and vad_open:
            vad_open = False
            speech_frames_in_window = 0
            last_partial_at_frame = 0
            last_partial_preview = ""

            if on_vad_state is not None:
                await on_vad_state(session, "ended")

            try:
                result = await stt_provider.flush_buffer()
            except Exception as exc:
                logger.exception(
                    "voice.stt_worker.flush_failed",
                    session_id=session.session_id,
                )
                if channel is not None and channel.is_open:
                    try:
                        await channel.send_error(
                            code="voice/stt/flush_failed",
                            detail=str(exc),
                        )
                    except Exception:
                        logger.warning(
                            "voice.stt_worker.error_notify_failed",
                            session_id=session.session_id,
                        )
                raise

            if result is None or not result.text:
                continue

            logger.info(
                "voice.stt_worker.transcription",
                session_id=session.session_id,
                text_length=len(result.text),
            )
            if on_final_transcription is not None:
                await on_final_transcription(session, result.text, language)


__all__ = [
    "run_stt_worker",
    "OnFinalTranscription",
    "OnPartialTranscription",
    "OnVadState",
]
