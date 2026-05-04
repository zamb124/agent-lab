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
from typing import Awaitable, Callable, Optional

from apps.voice.providers.base import BaseSTTProvider, BaseVADProvider
from apps.voice.services.voice_barge_in import BargeInController
from apps.voice.services.voice_client_channel import VoiceClientChannel
from apps.voice.services.voice_session import VoiceSession
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)

OnFinalTranscription = Optional[
    Callable[[VoiceSession, str, Optional[str]], Awaitable[None]]
]
OnPartialTranscription = Optional[
    Callable[[VoiceSession, str, Optional[str]], Awaitable[None]]
]
OnVadState = Optional[Callable[[VoiceSession, str], Awaitable[None]]]

_FRAME_DURATION_S = 0.02


async def run_stt_worker(
    session: VoiceSession,
    vad_provider: BaseVADProvider,
    stt_provider: BaseSTTProvider,
    *,
    on_final_transcription: OnFinalTranscription = None,
    on_vad_state: OnVadState = None,
    on_partial_transcription: OnPartialTranscription = None,
    barge_in: Optional[BargeInController] = None,
    language: Optional[str] = None,
    channel: Optional[VoiceClientChannel] = None,
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

    while session.active:
        try:
            audio_frame = await session.audio_in_queue.get()
        except asyncio.CancelledError:
            raise

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
            consume_preroll = getattr(vad_provider, "consume_preroll", None)
            if callable(consume_preroll):
                preroll = consume_preroll()
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
                    stt_preview_text="",
                    tts_is_active=True,
                )
            ):
                await barge_in.execute_barge_in(
                    session,
                    stt_provider=stt_provider,
                    vad_provider=vad_provider,
                )
                vad_open = False
                speech_frames_in_window = 0
                last_partial_at_frame = 0
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
                    await on_partial_transcription(
                        session, partial.text, language
                    )
            continue

        if not is_speech and vad_open:
            vad_open = False
            speech_frames_in_window = 0
            last_partial_at_frame = 0

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
