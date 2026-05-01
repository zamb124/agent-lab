"""Audio receiver — принимает бинарные фреймы из WebSocket и кладёт в очередь."""

from __future__ import annotations

import asyncio

from starlette.websockets import WebSocketDisconnect

from apps.voice.services.voice_session import VoiceSession
from core.logging import get_logger

logger = get_logger(__name__)


async def run_audio_receiver(
    session: VoiceSession,
    websocket,
) -> None:
    """Читает бинарные данные из WebSocket и складывает в audio_in_queue.

    Формат фрейма: PCM 16kHz, mono, 16-bit.
    """
    try:
        while session.active:
            data = await websocket.receive_bytes()
            if not session.active:
                break
            await session.audio_in_queue.put(data)
    except asyncio.CancelledError:
        raise
    except WebSocketDisconnect as exc:
        if exc.code != 1000:
            logger.warning(
                "voice.audio_receiver.ws_disconnect",
                session_id=session.session_id,
                code=exc.code,
                reason=exc.reason,
            )
    except Exception:
        logger.exception("voice.audio_receiver.error", session_id=session.session_id)
