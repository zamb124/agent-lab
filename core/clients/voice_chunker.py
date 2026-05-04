"""Чанкинг текста для TTS — общий утилитарный класс платформы.

Разбивает поток текста на куски, пригодные для потокового синтеза речи:

1. При встрече терминального знака (``.``, ``?``, ``!``, ``;``) — чанк готов.
2. Если буфер превысил ``chunk_max_chars`` — режем по ближайшей запятой.
3. Микрочанки (< ``min_words`` слов) — копятся дальше, чтобы не портить
   интонацию синтезированной речи.

Используется streaming-TTS-клиентами (`core.clients.tts_streaming`) и
speak-воркером voice-сессии (`apps/voice/services/speak_worker.py`).
"""

from __future__ import annotations

from core.logging import get_logger

logger = get_logger(__name__)


class VoiceChunker:
    """Интеллектуальное разделение текста для TTS."""

    def __init__(
        self,
        *,
        chunk_max_chars: int = 100,
        min_words: int = 3,
    ) -> None:
        if chunk_max_chars <= 0:
            raise ValueError("VoiceChunker: chunk_max_chars должен быть > 0.")
        if min_words <= 0:
            raise ValueError("VoiceChunker: min_words должен быть > 0.")
        self._chunk_max_chars = chunk_max_chars
        self._min_words = min_words
        self._buffer = ""

    def feed(self, text: str) -> list[str]:
        """Добавить текст и вернуть готовые чанки."""
        self._buffer += text
        chunks: list[str] = []

        while self._buffer:
            chunk, remainder = self._extract_chunk()
            if chunk is None:
                break
            chunks.append(chunk)
            self._buffer = remainder or ""

        return chunks

    def _extract_chunk(self) -> tuple[str | None, str]:
        """Извлечь один законченный чанк из буфера."""
        buf = self._buffer

        best_pos = -1
        for sep in (".", "?", "!", ";"):
            pos = buf.find(sep)
            if pos > 0 and (best_pos == -1 or pos < best_pos):
                best_pos = pos

        if best_pos > 0:
            chunk = buf[: best_pos + 1].strip()
            remainder = buf[best_pos + 1:]
            if self._words_in(chunk) >= self._min_words or len(self._buffer) > self._chunk_max_chars:
                return chunk, remainder

        if len(buf) >= self._chunk_max_chars:
            comma_pos = buf.rfind(",", 0, self._chunk_max_chars)
            if comma_pos > 0:
                chunk = buf[: comma_pos + 1].strip()
                remainder = buf[comma_pos + 1:]
                if self._words_in(chunk) >= self._min_words:
                    return chunk, remainder

        return None, buf

    def flush(self) -> str | None:
        """Забрать остаток буфера."""
        result = self._buffer.strip() if self._buffer.strip() else None
        self._buffer = ""
        return result

    @staticmethod
    def _words_in(text: str) -> int:
        return len(text.split())


__all__ = ["VoiceChunker"]
