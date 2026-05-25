"""Единая транспортная политика прерывания голоса (очереди TTS/STT/VAD).

История диалога и A2A живут на клиенте и в flows; здесь только согласованный
сброс аудио-пайплайна для всех триггеров (`barge_in`, `stop_playback`).
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING

from core.logging import get_logger

if TYPE_CHECKING:
    from apps.voice.providers.base import BaseSTTProvider, BaseVADProvider
    from apps.voice.services.voice_client_channel import VoiceClientChannel
    from apps.voice.services.voice_session import VoiceSession


logger = get_logger(__name__)


class VoiceTransportInterruptKind(Enum):
    """Причина транспортного прерывания на шлюзе voice."""

    BARGE_IN = "barge_in"
    STOP_PLAYBACK = "stop_playback"


async def execute_voice_transport_interrupt(
    *,
    session: "VoiceSession",
    kind: VoiceTransportInterruptKind,
    clear_tts_queues: bool,
    reset_stt_vad: bool,
    channel: VoiceClientChannel | None,
    stt_provider: BaseSTTProvider | None,
    vad_provider: BaseVADProvider | None,
    language: str | None,
    peek_min_buffer_bytes: int | None,
    on_barge_in_timestamp: Callable[[], None] | None,
) -> None:
    """Остановить TTS, опционально отправить снимок STT без flush, сбросить провайдеры.

    При barge-in до сброса STT вызывается ``peek_transcript`` (как partial), и при
    непустом тексте клиенту уходит ``transcript`` с ``final=True`` и
    ``interrupted=True`` — мост инициирует тот же путь, что и обычный final.
    Полный ``flush_buffer`` после barge-in запрещён: в буфере смешаны uplink и
    эхо TTS (`voice.mdc`).
    """
    if kind == VoiceTransportInterruptKind.BARGE_IN and on_barge_in_timestamp is not None:
        on_barge_in_timestamp()

    if reset_stt_vad and stt_provider is not None and peek_min_buffer_bytes is not None:
        if kind == VoiceTransportInterruptKind.BARGE_IN and channel is not None:
            try:
                peeked = await stt_provider.peek_transcript(
                    min_buffer_bytes=peek_min_buffer_bytes,
                )
            except Exception:
                logger.warning(
                    "voice.transport_interrupt.peek_failed",
                    session_id=session.session_id,
                    kind=kind.value,
                )
                peeked = None
            if peeked is not None and peeked.text.strip():
                text = peeked.text.strip()
                await channel.send_transcript(
                    text=text,
                    final=True,
                    language=language,
                    interrupted=True,
                )

    session.mark_tts_active(False)
    if clear_tts_queues:
        removed = session.clear_synthesis_and_audio_out()
    else:
        removed = 0
    if reset_stt_vad and stt_provider is not None:
        stt_provider.reset()
    if reset_stt_vad and vad_provider is not None:
        vad_provider.reset_state()
    logger.info(
        "voice.transport_interrupt.executed",
        session_id=session.session_id,
        kind=kind.value,
        removed_queue_items=removed,
        stt_reset=reset_stt_vad and stt_provider is not None,
        vad_reset=reset_stt_vad and vad_provider is not None,
    )


__all__ = [
    "VoiceTransportInterruptKind",
    "execute_voice_transport_interrupt",
]
