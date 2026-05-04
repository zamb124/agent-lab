"""STT worker — PCM → VAD → STT → text; публикует media-события.

Единственный источник правды для событий распознавания в voice-сессии:

* ``on_vad_state(session, "started"|"ended")`` — смена состояния VAD
  (первая речевая граница / окончание паузы);
* ``on_final_transcription(session, text, language)`` — финальная фраза
  после тишины: возврат от ``stt_provider.flush_buffer()``;
* при ``tts_is_active=True`` и срабатывании ``BargeInController`` —
  воркер сам вызывает ``execute_barge_in(session)``.

Никакой бизнес-логики: ни LLM, ни маршрутизации сообщений. Только
media-события, которые клиент (или универсальный ``VoiceClientChannel``)
транслирует в text-frames WS.
"""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from apps.voice.providers.base import BaseSTTProvider, BaseVADProvider
from apps.voice.services.voice_barge_in import BargeInController
from apps.voice.services.voice_client_channel import VoiceClientChannel
from apps.voice.services.voice_session import VoiceSession
from core.logging import get_logger

logger = get_logger(__name__)

OnFinalTranscription = Optional[
    Callable[[VoiceSession, str, Optional[str]], Awaitable[None]]
]
OnVadState = Optional[Callable[[VoiceSession, str], Awaitable[None]]]

_FRAME_DURATION_S = 0.02
_SILENCE_THRESHOLD = 10


async def run_stt_worker(
    session: VoiceSession,
    vad_provider: BaseVADProvider,
    stt_provider: BaseSTTProvider,
    *,
    on_final_transcription: OnFinalTranscription = None,
    on_vad_state: OnVadState = None,
    barge_in: Optional[BargeInController] = None,
    language: Optional[str] = None,
    channel: Optional[VoiceClientChannel] = None,
) -> None:
    """Пайплайн: audio_in_queue → VAD → STT → callbacks.

    При первой речевой границе вызывается ``on_vad_state(session, "started")``,
    после ``_SILENCE_THRESHOLD`` тихих фреймов — ``on_vad_state(session,
    "ended")`` и, если буфер не пуст, ``flush_buffer`` + ``on_final_transcription``.
    """
    speech_frames: int = 0
    silence_frames: int = 0
    vad_open: bool = False

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

        if is_speech:
            if not vad_open:
                vad_open = True
                if on_vad_state is not None:
                    await on_vad_state(session, "started")
            speech_frames += 1
            silence_frames = 0
            await stt_provider.push_audio(audio_frame)

            if (
                barge_in is not None
                and session.is_tts_active
                and barge_in.is_barge_in(
                    vad_speech_seconds=speech_frames * _FRAME_DURATION_S,
                    stt_preview_text="",
                    tts_is_active=True,
                )
            ):
                await barge_in.execute_barge_in(session)
        else:
            silence_frames += 1

            if vad_open and silence_frames >= _SILENCE_THRESHOLD:
                vad_open = False
                had_speech = speech_frames > 0
                speech_frames = 0
                silence_frames = 0

                if on_vad_state is not None:
                    await on_vad_state(session, "ended")

                if not had_speech:
                    continue

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


__all__ = ["run_stt_worker", "OnFinalTranscription", "OnVadState"]
