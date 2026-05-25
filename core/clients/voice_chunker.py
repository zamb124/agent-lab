"""Чанкинг текста для TTS — общий утилитарный класс платформы.

Разбивает поток текста на куски, пригодные для потокового синтеза речи:

1. При встрече терминального знака (``.``, ``?``, ``!``, ``;``) — чанк готов.
2. Если буфер превысил ``chunk_max_chars`` — режем по ближайшей запятой.
3. Микрочанки (< ``min_words`` слов) — копятся дальше, чтобы не портить
   интонацию синтезированной речи.

Используется streaming-TTS-клиентами (`core.clients.tts_streaming`) и
speak-воркером voice-сессии (`apps/voice/services/speak_worker.py`).

``flush()`` отдаёт остаток списком сегментов длиной не больше ``chunk_max_chars``,
чтобы бэкенды вроде Silero не получали один огромный ``input``.
"""

from __future__ import annotations


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
        self._chunk_max_chars: int = chunk_max_chars
        self._min_words: int = min_words
        self._buffer: str = ""

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

    def flush(self) -> list[str]:
        """Забрать остаток буфера (список сегментов, каждый ≤ ``chunk_max_chars``)."""
        raw = self._buffer
        self._buffer = ""
        buf = raw.strip()
        if not buf:
            return []

        max_c = self._chunk_max_chars
        if len(buf) <= max_c:
            return [buf]

        parts: list[str] = []
        rest = buf
        while rest:
            if len(rest) <= max_c:
                if rest.strip():
                    parts.append(rest)
                break
            cut = max_c
            sp = rest.rfind(" ", 0, cut)
            if sp > max_c // 2:
                cut = sp + 1
            piece = rest[:cut].strip()
            if not piece:
                piece = rest[:max_c].strip()
                cut = max_c
            parts.append(piece)
            rest = rest[cut:].lstrip()

        return [p for p in parts if p]

    @staticmethod
    def _words_in(text: str) -> int:
        return len(text.split())


__all__ = ["VoiceChunker"]
