"""Единый WS-воркер приёма: аудио (binary) + команды (text JSON).

Объединяет два потока входящих сообщений в одной корутине, чтобы избежать
гонки за ``websocket.receive()`` между параллельными читателями binary и
text (Starlette/FastAPI допускают только одного «реципиента» на сокет).

Контракт uplink (см. `voice.mdc`):

* ``binary`` — PCM 16kHz mono 16-bit → ``session.audio_in_queue``.
* text JSON с полем ``type``:

  - ``{"type":"config","session":{...}}`` — опциональное stateful config;
  - ``{"type":"speak","text":"..."}`` → ``session.synthesis_queue.put(text)``;
  - ``{"type":"end_of_utterance"}`` → ``session.synthesis_queue.put(_END_OF_UTTERANCE)``;
  - ``{"type":"stop_playback"}`` → сброс TTS + ``tts_state=stopped``.

Никаких неявных дефолтов: незнакомый ``type`` или payload без обязательных
полей → `send_error` клиенту с кодом ``voice/ws/bad_command``. Малформенный
JSON → ``voice/ws/bad_json``.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect

from apps.voice.services.speak_worker import (
    _END_OF_UTTERANCE,
    enqueue_end_of_utterance,
    enqueue_speak,
)
from apps.voice.services.voice_client_channel import VoiceClientChannel
from apps.voice.services.voice_session import VoiceSession
from core.logging import get_logger


logger = get_logger(__name__)


async def run_ws_receiver(
    session: VoiceSession,
    websocket: WebSocket,
    channel: VoiceClientChannel,
) -> None:
    """Читать WS-фреймы и раздавать их по назначению.

    Завершается при ``WebSocketDisconnect`` или когда ``session.active``
    становится False (cancel).
    """
    try:
        while session.active:
            message = await websocket.receive()
            msg_type = message.get("type")
            if msg_type == "websocket.disconnect":
                channel.mark_closed()
                return
            if msg_type != "websocket.receive":
                continue

            bytes_data = message.get("bytes")
            text_data = message.get("text")

            if bytes_data is not None:
                if not session.active:
                    return
                await session.audio_in_queue.put(bytes_data)
                continue

            if text_data is not None:
                await _handle_text_frame(
                    session=session, channel=channel, raw_text=text_data
                )
                continue
    except asyncio.CancelledError:
        raise
    except WebSocketDisconnect as exc:
        channel.mark_closed()
        if exc.code != 1000:
            logger.warning(
                "voice.ws_receiver.disconnect",
                session_id=session.session_id,
                code=exc.code,
                reason=exc.reason,
            )
    except Exception:
        logger.exception(
            "voice.ws_receiver.error",
            session_id=session.session_id,
        )


async def _handle_text_frame(
    *,
    session: VoiceSession,
    channel: VoiceClientChannel,
    raw_text: str,
) -> None:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        await channel.send_error(code="voice/ws/bad_json", detail=str(exc))
        return

    if not isinstance(payload, dict):
        await channel.send_error(
            code="voice/ws/bad_command",
            detail="Text frame must be a JSON object.",
        )
        return

    command = payload.get("type")
    if not isinstance(command, str) or command == "":
        await channel.send_error(
            code="voice/ws/bad_command",
            detail="Field 'type' is required.",
        )
        return

    if command == "speak":
        await _handle_speak(session=session, channel=channel, payload=payload)
        return

    if command == "end_of_utterance":
        await enqueue_end_of_utterance(session)
        return

    if command == "stop_playback":
        await _handle_stop_playback(session=session, channel=channel)
        return

    if command == "config":
        logger.info(
            "voice.ws_receiver.config_received",
            session_id=session.session_id,
            keys=list(payload.keys()),
        )
        return

    await channel.send_error(
        code="voice/ws/bad_command",
        detail=f"Unknown command type={command!r}.",
    )


async def _handle_speak(
    *,
    session: VoiceSession,
    channel: VoiceClientChannel,
    payload: dict[str, Any],
) -> None:
    text = payload.get("text")
    if not isinstance(text, str):
        await channel.send_error(
            code="voice/ws/bad_command",
            detail="speak: field 'text' must be string.",
        )
        return
    if text == "":
        return
    await enqueue_speak(session, text)

    final = payload.get("final")
    if final is True:
        await enqueue_end_of_utterance(session)


async def _handle_stop_playback(
    *,
    session: VoiceSession,
    channel: VoiceClientChannel,
) -> None:
    removed = session.clear_synthesis_and_audio_out()
    was_active = session.is_tts_active
    session.mark_tts_active(False)
    if was_active:
        await channel.send_tts_state("stopped")
    logger.info(
        "voice.ws_receiver.stop_playback",
        session_id=session.session_id,
        removed_queue_items=removed,
    )


__all__ = ["run_ws_receiver"]
