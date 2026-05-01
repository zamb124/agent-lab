"""Audio sender — забирает аудио из audio_out_queue и отправляет в WebSocket."""

from __future__ import annotations

import asyncio

from apps.voice.services.voice_session import VoiceSession
from core.logging import get_logger

logger = get_logger(__name__)


async def run_audio_sender(
    session: VoiceSession,
    websocket,
) -> None:
    """Отправляет TTS-аудио обратно клиенту через WebSocket."""
    while session.active:
        try:
            audio_bytes = await session.audio_out_queue.get()
        except asyncio.CancelledError:
            raise

        try:
            await websocket.send_bytes(audio_bytes)
            session.record_bytes_sent(len(audio_bytes))
        except Exception:
            logger.warning(
                "audio sender write error: session_id=%s",
                session.session_id,
            )
            break
