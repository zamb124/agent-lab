"""STT worker — берёт аудио из audio_in_queue, прогоняет через VAD и STT."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from apps.voice.providers.base import BaseSTTProvider, BaseVADProvider
from apps.voice.services.voice_barge_in import BargeInController
from apps.voice.services.voice_session import VoiceSession
from core.logging import get_logger

logger = get_logger(__name__)

_OnTranscription = Optional[Callable[[VoiceSession, str], Awaitable[None]]]

_FRAME_DURATION_S = 0.02


async def run_stt_worker(
    session: VoiceSession,
    vad_provider: BaseVADProvider,
    stt_provider: BaseSTTProvider,
    on_full_transcription: _OnTranscription = None,
    *,
    barge_in: Optional[BargeInController] = None,
) -> None:
    """Пайплайн: Audio → VAD → STT → текст (+ barge-in во время TTS).

    При обнаружении речи фреймы накапливаются через stt_provider.push_audio.
    После паузы (10 тихих фреймов) вызывается flush_buffer для получения
    транскрипции. Если задан `barge_in` — речь во время активного TTS
    может прервать его (очистить synthesis_queue / audio_out_queue).
    """
    speech_frames: int = 0
    silence_frames: int = 0
    SILENCE_THRESHOLD = 10

    while session.active:
        try:
            audio_frame = await session.audio_in_queue.get()
        except asyncio.CancelledError:
            raise

        try:
            is_speech = await vad_provider.detect_speech(audio_frame, sample_rate=16000)
        except Exception:
            logger.warning("VAD error, skipping frame: session_id=%s", session.session_id)
            continue

        if is_speech:
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

            if speech_frames > 0 and silence_frames >= SILENCE_THRESHOLD:
                speech_frames = 0
                silence_frames = 0

                result = await stt_provider.flush_buffer()

                if result is not None and result.text:
                    logger.info(
                        "STT транскрипция: session_id=%s text=%s",
                        session.session_id,
                        result.text,
                    )
                    await session.text_in_queue.put(result.text)
                    if on_full_transcription:
                        await on_full_transcription(session, result.text)
