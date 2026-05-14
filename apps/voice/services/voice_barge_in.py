"""Barge-in controller — обработка пользовательских прерываний."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from apps.voice.providers.base import BaseSTTProvider, BaseVADProvider
from apps.voice.services.voice_transport_interrupt import (
    VoiceTransportInterruptKind,
    execute_voice_transport_interrupt,
)

if TYPE_CHECKING:
    from apps.voice.services.voice_client_channel import VoiceClientChannel


class BargeInController:
    """Каскад детекции прерываний: VAD-уровень → SmartTurn."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        smart_turn_buffer_ms: int = 500,
        command_words: list[str] | None = None,
        flush_timeout_ms: int = 200,
        cooldown_ms: int = 300,
    ) -> None:
        self._enabled = enabled
        self._smart_turn_buffer_ms = smart_turn_buffer_ms
        self._command_words = command_words or ["стоп", "хватит", "подожди", "стоп"]
        self._flush_timeout_ms = flush_timeout_ms
        self._cooldown_ms = cooldown_ms
        self._last_barge_in_ts: float = 0
        self._pending_audio_buffer: list[bytes] = []
        self._speech_start_ts: float | None = None

    def record_speech_start(self) -> None:
        self._speech_start_ts = time.monotonic()

    def is_barge_in(
        self,
        *,
        vad_speech_seconds: float,
        stt_preview_text: str,
        tts_is_active: bool,
    ) -> bool:
        """Определить, является ли речь прерыванием (barge-in)."""
        if not self._enabled:
            return False

        now = time.monotonic()
        if (now - self._last_barge_in_ts) * 1000 < self._cooldown_ms:
            return False

        if vad_speech_seconds < 0.3:
            return False

        if not tts_is_active:
            return False

        words_lower = stt_preview_text.lower()
        for word in self._command_words:
            if word in words_lower:
                return True

        if vad_speech_seconds >= self._smart_turn_buffer_ms / 1000:
            return True

        return False

    def mark_barge_in_executed(self) -> None:
        """Обновить время последнего barge-in (cooldown в `is_barge_in`)."""
        self._last_barge_in_ts = time.monotonic()

    async def execute_barge_in(
        self,
        session,
        clear_tts_queue: bool = True,
        *,
        stt_provider: Optional[BaseSTTProvider] = None,
        vad_provider: Optional[BaseVADProvider] = None,
        channel: Optional["VoiceClientChannel"] = None,
        language: Optional[str] = None,
        peek_min_buffer_bytes: Optional[int] = None,
    ) -> None:
        """Остановить TTS, очистить очереди синтеза/исходящего аудио и
        сбросить внутреннее состояние STT/VAD-провайдеров.

        Сброс STT/VAD обязателен: накопленный к моменту прерывания PCM —
        это аудио уходящего ответа TTS, а не следующая фраза пользователя;
        флэш этого буфера в финальный transcript даёт «чужие» слова.
        Перед сбросом — один ``peek_transcript`` и при непустом тексте
        `transcript` на клиент (`voice_transport_interrupt`).
        """
        await execute_voice_transport_interrupt(
            session=session,
            kind=VoiceTransportInterruptKind.BARGE_IN,
            clear_tts_queues=clear_tts_queue,
            reset_stt_vad=True,
            channel=channel,
            stt_provider=stt_provider,
            vad_provider=vad_provider,
            language=language,
            peek_min_buffer_bytes=peek_min_buffer_bytes,
            on_barge_in_timestamp=self.mark_barge_in_executed,
        )


