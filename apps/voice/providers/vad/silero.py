"""Silero VAD provider — детекция речи на CPU."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Optional

from apps.voice.providers.base import BaseVADProvider
from core.logging import get_logger

logger = get_logger(__name__)


class SileroVADProvider(BaseVADProvider):
    """Silero VAD для обнаружения речи в аудио-фреймах.

    Работает на CPU, задержка ~30ms на фрейм.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        threshold: float = 0.5,
    ) -> None:
        self._sample_rate = sample_rate
        self._threshold = threshold
        self._model: Optional[Any] = None
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None

    async def init(self) -> None:
        """Загрузить модель Silero VAD."""
        from silero_vad import load_silero_vad

        model, utils = load_silero_vad()
        _get_speech_ts = utils[0]

        self._model = (model, _get_speech_ts)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        logger.info("Silero VAD загружен (sample_rate=%d, threshold=%.2f)", self._sample_rate, self._threshold)

    async def detect_speech(self, audio_pcm: bytes, sample_rate: int) -> bool:
        """Определить наличие речи в аудиофрейме."""
        if self._model is None:
            raise RuntimeError("SileroVADProvider не инициализирован (вызовите init)")

        if sample_rate != self._sample_rate:
            raise ValueError(
                f"Ожидается sample_rate={self._sample_rate}, получено {sample_rate}"
            )

        import struct

        audio_int16 = struct.unpack("<" + "h" * (len(audio_pcm) // 2), audio_pcm)
        import torch

        audio_tensor = torch.tensor([float(x) / 32768.0], dtype=torch.float32)

        model, get_speech_ts = self._model

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self._executor,
            get_speech_ts,
            audio_tensor,
            model,
            self._sample_rate,
            self._threshold,
        )

        return len(result) > 0

    def reset_state(self) -> None:
        if self._model is not None:
            model, _ = self._model
            try:
                model.reset_states()
            except Exception:
                pass

    async def close(self) -> None:
        """Выгрузить модель Silero VAD."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
        self._model = None
        logger.info("Silero VAD выгружен")
