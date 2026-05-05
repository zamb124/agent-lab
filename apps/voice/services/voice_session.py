"""Управление жизненным циклом голосовой сессии."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Union

from core.logging import get_logger

logger = get_logger(__name__)


MicAudioInItem = Union[bytes, "MicFinalizeRequest"]


@dataclass(slots=True)
class MicFinalizeRequest:
    """Помещается в ``audio_in_queue`` по WS-команде ``end_recording``.

    После синхронного flush очередной фразы (если VAD считает сегмент открытым)
    stt_worker сигнализирует ``complete``: ws_receiver может дождаться и ответить
    клиенту текстом ``finalize_done`` до закрытия сокета.
    """

    complete: asyncio.Future[None]


class VoiceSession:
    """Одна голосовая сессия клиента.

    Содержит очереди для асинхронного обмена аудио и текстом
    между воркерами обработки.
    """

    def __init__(
        self,
        *,
        session_id: str,
        audio_in_size: int = 1024,
        audio_out_size: int = 256,
        text_size: int = 256,
        synthesis_size: int = 64,
    ) -> None:
        self.session_id = session_id
        self.created_at = time.monotonic()

        self.audio_in_queue: asyncio.Queue[MicAudioInItem] = asyncio.Queue(
            maxsize=audio_in_size
        )
        self.audio_out_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=audio_out_size)
        self.text_in_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=text_size)
        self.synthesis_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=synthesis_size)

        self._active = True
        self._tasks: list[asyncio.Task] = []
        self._bytes_sent: int = 0
        self._bytes_received: int = 0
        self._pcm_chunk_count: int = 0
        self._is_tts_active: bool = False

    def mark_tts_active(self, active: bool) -> None:
        """Отметить, что TTS в данный момент активен (для AEC VAD)."""
        self._is_tts_active = active

    @property
    def tts_active(self) -> bool:
        return self._is_tts_active

    @property
    def is_tts_active(self) -> bool:
        return self._is_tts_active

    def add_bytes_sent(self, count: int) -> None:
        self._bytes_sent += count

    def add_bytes_received(self, count: int) -> None:
        self._bytes_received += count

    def record_pcm_chunk_from_client(self, byte_len: int) -> int:
        """Учесть один бинарный PCM-кадр uplink; возвращает порядковый номер chunk."""
        if byte_len <= 0:
            raise ValueError("VoiceSession.record_pcm_chunk_from_client: byte_len должен быть > 0.")
        self.add_bytes_received(byte_len)
        self._pcm_chunk_count += 1
        return self._pcm_chunk_count

    @property
    def pcm_chunk_count(self) -> int:
        return self._pcm_chunk_count

    def record_bytes_sent(self, count: int) -> None:
        self._bytes_sent += count

    @property
    def bytes_sent(self) -> int:
        return self._bytes_sent

    @property
    def bytes_received(self) -> int:
        return self._bytes_received

    def add_task(self, task: asyncio.Task) -> None:
        self._tasks.append(task)

    async def enqueue_mic_finalize(self, req: MicFinalizeRequest) -> None:
        """Поставить в очередь обработки uplink запрос на немедленный flush STT-буфера."""
        if req.complete.done():
            raise ValueError("MicFinalizeRequest.complete уже завершён.")
        if not self._active:
            req.complete.set_exception(
                RuntimeError("VoiceSession: сессия уже не активна.")
            )
            return
        await self.audio_in_queue.put(req)

    async def cancel(self) -> None:
        """Остановить все воркеры сессии."""
        self._active = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()
        self._clear_queues()
        logger.info("voice session cancelled: session_id=%s", self.session_id)

    def _clear_queues(self) -> None:
        self._drain_audio_in_queue(self.audio_in_queue)
        for q in (
            self.audio_out_queue,
            self.text_in_queue,
            self.synthesis_queue,
        ):
            self._drain_simple_queue(q)

    def clear_synthesis_and_audio_out(self) -> int:
        """Сбросить очереди синтеза и исходящего аудио (для barge-in).

        Возвращает суммарное количество удалённых элементов.
        """
        return self._drain_simple_queue(self.synthesis_queue) + self._drain_simple_queue(
            self.audio_out_queue
        )

    @staticmethod
    def _drain_audio_in_queue(q: asyncio.Queue[MicAudioInItem]) -> int:
        removed = 0
        while not q.empty():
            try:
                item = q.get_nowait()
            except asyncio.QueueEmpty:
                break
            removed += 1
            if isinstance(item, MicFinalizeRequest):
                if not item.complete.done():
                    item.complete.cancel()
        return removed

    @staticmethod
    def _drain_simple_queue(q: asyncio.Queue) -> int:
        removed = 0
        while not q.empty():
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                break
            removed += 1
        return removed

    @property
    def active(self) -> bool:
        return self._active


__all__ = [
    "MicAudioInItem",
    "MicFinalizeRequest",
    "VoiceSession",
]
