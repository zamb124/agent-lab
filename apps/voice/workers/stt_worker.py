"""STT worker — берёт аудио из audio_in_queue, прогоняет через VAD и STT."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Optional

from apps.voice.providers.base import BaseSTTProvider, BaseVADProvider
from apps.voice.services.voice_session import VoiceSession
from core.logging import get_logger

logger = get_logger(__name__)

_OnTranscription = Optional[Callable[[VoiceSession, str], Awaitable[None]]]


async def run_stt_worker(
    session: VoiceSession,
    vad_provider: BaseVADProvider,
    stt_provider: BaseSTTProvider,
    on_full_transcription: _OnTranscription = None,
) -> None:
    """Пайплайн: Audio → VAD → STT → текст.

    При обнаружении речи фреймы накапливаются через stt_provider.push_audio.
    После паузы (10 тихих фреймов) вызывается flush_buffer для получения транскрипции.
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
                    if on_full_transcription:
                        await on_full_transcription(session, result.text)
