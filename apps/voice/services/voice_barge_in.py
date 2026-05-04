"""Barge-in controller — обработка пользовательских прерываний."""

from __future__ import annotations

import time
from typing import Optional

from apps.voice.providers.base import BaseSTTProvider, BaseVADProvider
from core.logging import get_logger

logger = get_logger(__name__)


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

    async def execute_barge_in(
        self,
        session,
        clear_tts_queue: bool = True,
        *,
        stt_provider: Optional[BaseSTTProvider] = None,
        vad_provider: Optional[BaseVADProvider] = None,
    ) -> None:
        """Остановить TTS, очистить очереди синтеза/исходящего аудио и
        сбросить внутреннее состояние STT/VAD-провайдеров.

        Сброс STT/VAD обязателен: накопленный к моменту прерывания PCM —
        это аудио уходящего ответа TTS, а не следующая фраза пользователя;
        флэш этого буфера в финальный transcript даёт «чужие» слова.
        """
        self._last_barge_in_ts = time.monotonic()
        session.mark_tts_active(False)
        if clear_tts_queue:
            removed = session.clear_synthesis_and_audio_out()
        else:
            removed = 0
        if stt_provider is not None:
            stt_provider.reset()
        if vad_provider is not None:
            vad_provider.reset_state()
        logger.info(
            "voice.barge_in.executed",
            session_id=session.session_id,
            removed_queue_items=removed,
            stt_reset=stt_provider is not None,
            vad_reset=vad_provider is not None,
        )
