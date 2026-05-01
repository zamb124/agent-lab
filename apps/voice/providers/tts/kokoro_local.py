"""Kokoro TTS provider — синтез речи на CPU (82M params)."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from apps.voice.providers.base import BaseTTSProvider
from core.logging import get_logger

logger = get_logger(__name__)


class KokoroLocalTTSProvider(BaseTTSProvider):
    """Kokoro TTS работает локально на CPU/ONNX.

    Требует onnxruntime. Модель загружается лениво при init.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 24000,
        model_path: str | None = None,
        accelerator: str = "cpu",
    ) -> None:
        self._sample_rate = sample_rate
        self._model_path = model_path
        self._accelerator = accelerator
        self._model: Any | None = None
        self._initialized = False

    def _ensure_model(self) -> Any:
        """Лениво загружает Kokoro TTS модель."""
        if self._model is None:
            from kokoro import KPipeline

            self._model = KPipeline(lang="ru")
        return self._model

    async def init(self) -> None:
        """Загрузить модель синтезатора."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ensure_model)
        self._initialized = True
        logger.info("Kokoro TTS загружен (sample_rate=%d)", self._sample_rate)

    async def synthesize(self, text: str) -> bytes:
        """Синтезировать текст в PCM-байты."""
        if not self._initialized:
            raise RuntimeError("KokoroLocalTTSProvider не инициализирован")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> bytes:
        """Однократный вызов Kokoro."""
        pipeline = self._ensure_model()
        audio_chunks = []
        for _, _, audio in pipeline(text):
            if audio is not None:
                audio_chunks.append(audio.tobytes())
        if not audio_chunks:
            raise ValueError(f"Kokoro не вернул аудио для текста: {text[:50]!r}")
        return b"".join(audio_chunks)

    async def close(self) -> None:
        self._model = None
        self._initialized = False
