"""WebSocket session endpoint для voice-сервиса."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.voice.container import get_voice_container
from apps.voice.services.voice_chunker import VoiceChunker
from apps.voice.services.voice_session import VoiceSession
from apps.voice.workers.audio_receiver import run_audio_receiver
from apps.voice.workers.audio_sender import run_audio_sender
from apps.voice.workers.stt_worker import run_stt_worker
from apps.voice.workers.tts_worker import run_tts_worker
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/ws/session",
    tags=["voice-websocket"],
)


@router.websocket("/{session_id}")
async def voice_session(websocket: WebSocket, session_id: str) -> None:
    """WebSocket соединение для голосового стрима.

    Принимает PCM 16kHz mono 16-bit, возвращает аудио от TTS.
    """
    await websocket.accept()
    logger.info("voice client connected: session_id=%s", session_id)

    container = get_voice_container()
    session = VoiceSession(session_id=session_id)

    vad_provider = container.vad_provider
    stt_provider = container.stt_provider
    tts_provider = container.tts_provider

    chunker = VoiceChunker()

    async def _on_full_transcription(sess: VoiceSession, text: str) -> None:
        logger.info(
            "voice/transcription/completed: session_id=%s text=%s",
            sess.session_id,
            text,
        )

    async def _on_error(sess: VoiceSession, code: str, detail: str) -> None:
        try:
            await websocket.send_json({"type": "error", "code": code, "detail": detail})
        except Exception:
            pass

    async def send_heartbeat(sess: VoiceSession, ws: WebSocket) -> None:
        """Периодически шлёт пинг для удержания соединения."""
        while sess.active:
            try:
                await asyncio.sleep(30)
                if not sess.active:
                    break
                await ws.send_json({"type": "ping"})
            except asyncio.CancelledError:
                raise
            except Exception:
                break

    try:
        all_tasks = []

        all_tasks.append(asyncio.create_task(run_audio_receiver(session, websocket)))
        session.add_task(all_tasks[-1])

        all_tasks.append(asyncio.create_task(run_stt_worker(
            session, vad_provider, stt_provider,
            on_full_transcription=_on_full_transcription,
        )))
        session.add_task(all_tasks[-1])

        all_tasks.append(asyncio.create_task(run_tts_worker(
            session, tts_provider, chunker,
        )))
        session.add_task(all_tasks[-1])

        all_tasks.append(asyncio.create_task(run_audio_sender(session, websocket)))
        session.add_task(all_tasks[-1])

        all_tasks.append(asyncio.create_task(send_heartbeat(session, websocket)))
        session.add_task(all_tasks[-1])

        await asyncio.gather(*all_tasks, return_exceptions=True)

    except WebSocketDisconnect:
        logger.info("voice client disconnected: session_id=%s", session_id)
    except Exception:
        logger.exception("voice session error: session_id=%s", session_id)
    finally:
        await session.cancel()
        logger.info("voice session cleanup done: session_id=%s", session_id)
