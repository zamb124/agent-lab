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
import os
import time
from typing import Any, Optional

from starlette.websockets import WebSocket, WebSocketDisconnect

from apps.voice.services.speak_worker import (
    _END_OF_UTTERANCE,
    enqueue_end_of_utterance,
    enqueue_speak,
)
from apps.voice.services.voice_client_channel import VoiceClientChannel
from apps.voice.services.voice_session import VoiceSession
from core.config import get_settings
from core.files.media.pcm_to_wav import pcm_s16le_mono_to_wav
from core.logging import get_logger


logger = get_logger(__name__)


_UPLINK_DUMP_SAMPLE_RATE = 16000


def _safe_session_id_for_filename(session_id: str) -> str:
    """Оставить только safe-символы (`a-zA-Z0-9_.-`); остальное — на ``_``."""
    out = []
    for ch in session_id:
        if ch.isalnum() or ch in ("_", ".", "-"):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out) or "session"


class _UplinkDump:
    """Накапливает сырой PCM от клиента и на закрытии WS пишет WAV-файл.

    Включается заданием ``settings.voice.diagnostics.uplink_dump_dir``;
    лимит по размеру — ``uplink_dump_max_mb``. Используется только в dev
    для диагностики проблем STT (расхождение слышимого vs распознанного).
    """

    def __init__(self, *, dump_dir: str, max_bytes: int, session_id: str) -> None:
        if dump_dir == "":
            raise ValueError("_UplinkDump: dump_dir не может быть пустым.")
        if max_bytes <= 0:
            raise ValueError("_UplinkDump: max_bytes должен быть > 0.")
        self._dump_dir = dump_dir
        self._max_bytes = max_bytes
        self._session_id = session_id
        self._buffer = bytearray()
        self._truncated = False

    def append(self, pcm_chunk: bytes) -> None:
        if not pcm_chunk or self._truncated:
            return
        remaining = self._max_bytes - len(self._buffer)
        if remaining <= 0:
            self._truncated = True
            return
        if len(pcm_chunk) <= remaining:
            self._buffer.extend(pcm_chunk)
        else:
            self._buffer.extend(pcm_chunk[:remaining])
            self._truncated = True

    def finalize(self) -> Optional[str]:
        if not self._buffer:
            return None
        os.makedirs(self._dump_dir, exist_ok=True)
        ts = int(time.time())
        name = (
            f"voice_uplink_{_safe_session_id_for_filename(self._session_id)}_"
            f"{ts}.wav"
        )
        path = os.path.join(self._dump_dir, name)
        wav = pcm_s16le_mono_to_wav(
            bytes(self._buffer), sample_rate=_UPLINK_DUMP_SAMPLE_RATE
        )
        with open(path, "wb") as fp:
            fp.write(wav)
        logger.info(
            "voice.ws_receiver.uplink_dump_saved",
            session_id=self._session_id,
            path=path,
            bytes=len(self._buffer),
            truncated=self._truncated,
        )
        return path


def _build_uplink_dump(session_id: str) -> Optional[_UplinkDump]:
    cfg = get_settings().voice.diagnostics
    if cfg.uplink_dump_dir is None or cfg.uplink_dump_dir == "":
        return None
    return _UplinkDump(
        dump_dir=cfg.uplink_dump_dir,
        max_bytes=cfg.uplink_dump_max_mb * 1024 * 1024,
        session_id=session_id,
    )


async def run_ws_receiver(
    session: VoiceSession,
    websocket: WebSocket,
    channel: VoiceClientChannel,
) -> None:
    """Читать WS-фреймы и раздавать их по назначению.

    Завершается при ``WebSocketDisconnect`` или когда ``session.active``
    становится False (cancel). При включённой диагностике
    (``voice.diagnostics.uplink_dump_dir``) сохраняет полученный PCM в
    WAV на закрытии.
    """
    dump = _build_uplink_dump(session.session_id)
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
                ln = len(bytes_data)
                if ln == 0:
                    logger.warning(
                        "voice.ws_receiver.empty_pcm_frame",
                        session_id=session.session_id,
                    )
                    continue
                chunk_seq = session.record_pcm_chunk_from_client(ln)
                await session.audio_in_queue.put(bytes_data)
                if dump is not None:
                    dump.append(bytes_data)
                if chunk_seq == 1 or chunk_seq % 128 == 0:
                    logger.info(
                        "voice.ws_receiver.pcm_received",
                        session_id=session.session_id,
                        chunk_seq=chunk_seq,
                        byte_len=ln,
                        bytes_received_total=session.bytes_received,
                    )
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
    finally:
        if dump is not None:
            try:
                dump.finalize()
            except Exception:
                logger.exception(
                    "voice.ws_receiver.uplink_dump_failed",
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
