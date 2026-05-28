"""Ошибки LLM-клиента и константы таймингов stream."""

from __future__ import annotations


class LLMStreamUserCancelledError(Exception):
    """Отмена flow обнаружена при чтении LLM stream."""


class LLMStreamIdleTimeoutError(Exception):
    """SSE stream не отдавал чанки дольше настроенного idle-лимита."""

    def __init__(self, idle_seconds: float, chunks_received: int):
        self.idle_seconds: float = idle_seconds
        self.chunks_received: int = chunks_received
        super().__init__(
            f"LLM stream idle timeout: no data for {idle_seconds:.1f}s "
            + f"after {chunks_received} chunks received"
        )


# Максимальное время ожидания между чанками SSE-стрима (секунды).
STREAM_IDLE_TIMEOUT_SECONDS: float = 10.0

# Warning-порог: если между чанками > N секунд — логируем предупреждение.
INTER_CHUNK_WARN_SECONDS: float = 5.0


__all__ = [
    "INTER_CHUNK_WARN_SECONDS",
    "LLMStreamIdleTimeoutError",
    "LLMStreamUserCancelledError",
    "STREAM_IDLE_TIMEOUT_SECONDS",
]
