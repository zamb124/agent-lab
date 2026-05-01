"""Чанкинг текста для TTS."""

from __future__ import annotations

from core.logging import get_logger

logger = get_logger(__name__)


class VoiceChunker:
    """Интеллектуальное разделение текста для TTS.

    Алгоритм:
    1. Ищем терминальные знаки `.`, `?`, `!`, `;` → чанк готов
    2. Если буфер > chunk_max_chars — делим по `,`
    3. Защита от микро-чанков: < min_words → пропускаем
    """

    def __init__(
        self,
        *,
        chunk_max_chars: int = 100,
        min_words: int = 3,
    ) -> None:
        self._chunk_max_chars = chunk_max_chars
        self._min_words = min_words
        self._buffer = ""

    def feed(self, text: str) -> list[str]:
        """Добавить текст и вернуть готовые чанки."""
        self._buffer += text
        chunks = []

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

        # Ищем ближайший терминатор (не первый по типу, а первый по позиции)
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
