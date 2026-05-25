"""Типизированный канал отправки фреймов клиенту voice-сессии.

Одна voice WS-сессия имеет несколько источников исходящих сообщений:

* ``speak_worker`` — PCM байты (TTS) + события ``tts_state``;
* ``stt_worker`` — ``transcript`` и ``vad`` text-frames;
* ``send_heartbeat`` — ``ping``;
* ``error_reporter`` — ``error`` из любого воркера.

Все они пишут в один и тот же ``WebSocket``, поэтому доступ должен быть
сериализован (``asyncio.Lock``) — иначе кадры перемешаются. Канал — единая
точка отправки: все исходящие фреймы проходят через типизированные методы,
никаких прямых ``websocket.send_*`` из воркеров.

Контракт фреймов (`voice.mdc`):

* binary downlink — чанки TTS в формате из первого ``media_config`` (часто
    WAV по ``mime`` / ``sample_rate`` текущего TTS-провайдера);
* binary uplink от клиента — только PCM **s16le mono 16000 Hz** см. поле ``uplink`` в ``media_config``.
* text JSON:
    - ``{"type":"transcript","text":"...","final":true|false,"language":"ru"}``
    - ``{"type":"vad","state":"started"|"ended"}``
    - ``{"type":"tts_state","state":"playing"|"stopped"}``
    - ``{"type":"error","code":"...","detail":"..."}``
    - ``{"type":"ping"}``
    - ``{"type":"finalize_done"}`` — ответ на ``end_recording`` (flush STT выполнен)
"""

from __future__ import annotations

import asyncio
from typing import Literal, Protocol

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from apps.voice.models import VoiceClientJsonFrame, VoiceTranscriptFrame
from core.logging import get_logger

logger = get_logger(__name__)


VadState = Literal["started", "ended"]
TtsState = Literal["playing", "stopped"]


class VoiceSynthesisChannel(Protocol):
    """Минимальный контракт канала, который нужен speak-worker."""

    async def send_pcm(self, audio_bytes: bytes) -> None: ...

    async def send_tts_state(self, state: TtsState) -> None: ...

    async def send_error(self, *, code: str, detail: str) -> None: ...


class VoiceClientChannel:
    """Сериализованный исходящий канал WS-сессии voice.

    Все методы ``send_*`` берут внутренний ``asyncio.Lock`` на время
    одной отправки, поэтому никогда не бросают ошибок вида
    «concurrent write to websocket».
    """

    def __init__(self, websocket: WebSocket, *, session_id: str) -> None:
        if session_id == "":
            raise ValueError("VoiceClientChannel: session_id не может быть пустым.")
        self._websocket: WebSocket = websocket
        self._session_id: str = session_id
        self._lock: asyncio.Lock = asyncio.Lock()
        self._closed: bool = False

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_open(self) -> bool:
        """True, если соединение ещё валидно для отправки."""
        if self._closed:
            return False
        return self._websocket.application_state == WebSocketState.CONNECTED

    def mark_closed(self) -> None:
        """Пометить канал закрытым (после `WebSocketDisconnect`)."""
        self._closed = True

    async def send_media_config(
        self,
        *,
        mime_type: str,
        sample_rate: int,
        channels: int = 1,
    ) -> None:
        """Сообщить клиенту параметры исходящего аудио (TTS) и зафиксировать uplink PCM.

        Поля ``mime`` / ``sample_rate`` / ``channels`` относятся только к **бинарному
        потоку от сервера** (синтез речи). Микрофон клиента всегда шлётся отдельным
        бинарным PCM по полю ``uplink`` (контракт см. ``ws_receiver``).

        Отправляется один раз сразу после принятия WS.
        """
        if mime_type == "":
            raise ValueError("VoiceClientChannel.send_media_config: mime_type обязателен.")
        if sample_rate <= 0:
            raise ValueError("VoiceClientChannel.send_media_config: sample_rate > 0.")
        if channels <= 0:
            raise ValueError("VoiceClientChannel.send_media_config: channels > 0.")
        await self._send_json({
            "type": "media_config",
            "mime": mime_type,
            "sample_rate": sample_rate,
            "channels": channels,
            "uplink": {
                "encoding": "pcm_s16le",
                "sample_rate": 16_000,
                "channels": 1,
            },
        })

    async def send_pcm(self, audio_bytes: bytes) -> None:
        """Отправить PCM-чанк синтезированной речи клиенту."""
        if len(audio_bytes) == 0:
            return
        if not self.is_open:
            return
        async with self._lock:
            if not self.is_open:
                return
            await self._websocket.send_bytes(audio_bytes)

    async def send_transcript(
        self,
        *,
        text: str,
        final: bool,
        language: str | None = None,
        interrupted: bool = False,
    ) -> None:
        """Передать клиенту результат STT (partial или final)."""
        payload: VoiceTranscriptFrame = {
            "type": "transcript",
            "text": text,
            "final": final,
        }
        if language is not None and language != "":
            payload["language"] = language
        if interrupted:
            payload["interrupted"] = True
        await self._send_json(payload)

    async def send_vad(self, state: VadState) -> None:
        """Сообщить клиенту о смене VAD-состояния."""
        await self._send_json({"type": "vad", "state": state})

    async def send_tts_state(self, state: TtsState) -> None:
        """Сообщить клиенту, что TTS начал/закончил воспроизведение."""
        await self._send_json({"type": "tts_state", "state": state})

    async def send_error(self, *, code: str, detail: str) -> None:
        """Отправить клиенту ошибку media-уровня."""
        if code == "":
            raise ValueError("VoiceClientChannel.send_error: code обязателен.")
        await self._send_json({"type": "error", "code": code, "detail": detail})

    async def send_ping(self) -> None:
        """Keep-alive heartbeat."""
        await self._send_json({"type": "ping"})

    async def send_recording_finalized(self) -> None:
        """Подтвердить клиенту завершение обработки команды ``end_recording``.

        После финального/transcript может не быть (буфер пуст); клиент всё равно
        переходит к закрытию локальной сессии.
        """
        await self._send_json({"type": "finalize_done"})

    async def _send_json(self, payload: VoiceClientJsonFrame) -> None:
        if not self.is_open:
            return
        async with self._lock:
            if not self.is_open:
                return
            await self._websocket.send_json(payload)


__all__ = ["VoiceClientChannel", "VadState", "TtsState"]
