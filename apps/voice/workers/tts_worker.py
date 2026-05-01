"""TTS worker — берёт текст из text_in_queue и кладёт аудио в audio_out_queue."""

from __future__ import annotations

import asyncio

from apps.voice.services.voice_chunker import VoiceChunker
from apps.voice.services.voice_session import VoiceSession
from core.logging import get_logger

logger = get_logger(__name__)


async def run_tts_worker(
    session: VoiceSession,
    tts_provider,
    chunker: VoiceChunker | None = None,
) -> None:
    """Пайплайн: Текст → чанкинг → синтез → audio_out_queue."""
    if chunker is None:
        chunker = VoiceChunker()

    while session.active:
        try:
            text_batch = await session.text_in_queue.get()
        except asyncio.CancelledError:
            raise

        session.mark_tts_active(True)

        try:
            chunks = chunker.feed(text_batch)
            for chunk in chunks:
                audio_bytes = await tts_provider.synthesize(chunk)
                await session.audio_out_queue.put(audio_bytes)

            remainder = chunker.flush()
            if remainder:
                audio_bytes = await tts_provider.synthesize(remainder)
                await session.audio_out_queue.put(audio_bytes)
        except Exception:
            logger.exception("TTS synthesis failed: session_id=%s", session.session_id)
        finally:
            session.mark_tts_active(False)
