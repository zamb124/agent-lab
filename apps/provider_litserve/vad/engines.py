"""Движок для локального VAD в provider_litserve.

Список доступных моделей и их параметры (``sample_rate``, ``threshold``)
берутся из ``cfg.vad_models``. Дефолт — ``cfg.vad_default_api_model_id``.

Бэкенд по умолчанию — Silero VAD. При расширении ``cfg.vad_models`` другими
моделями сюда подключаются их адаптеры — диспатч по ``api_model_id``.
"""

from __future__ import annotations

import struct
import time
from typing import Any

from apps.provider_litserve.model_registry import find_vad_entry
from apps.provider_litserve.runtime_models import (
    allowed_api_model_ids,
    resolve_hf_model_id,
)
from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveVADModelEntry,
)
from core.logging import get_logger

logger = get_logger(__name__)


def parse_vad_body(raw: Any, *, default_api_model_id: str) -> dict[str, Any]:
    """Разобрать тело VAD-запроса.

    Поля: ``audio`` (PCM bytes) или ``file``, ``model`` (опционально, api id),
    ``sample_rate`` (опционально, переопределяет дефолт модели).
    """
    if not isinstance(raw, dict):
        raise ValueError("VAD: тело запроса должно быть JSON-объектом")
    audio_bytes = raw.get("audio") or raw.get("file")
    if not audio_bytes:
        raise ValueError("VAD: поле audio (или file) обязательно")
    if not isinstance(audio_bytes, bytes):
        audio_bytes = bytes(audio_bytes)

    requested_model = str(raw.get("model") or "").strip()
    if requested_model == "":
        requested_model = default_api_model_id.strip()
    if requested_model == "":
        raise ValueError(
            "VAD: model обязателен (либо явно, либо vad_default_api_model_id в конфиге)"
        )

    sample_rate_raw = raw.get("sample_rate")
    sample_rate = int(sample_rate_raw) if sample_rate_raw is not None else None
    return {
        "audio_bytes": audio_bytes,
        "model": requested_model,
        "sample_rate_override": sample_rate,
    }


class LocalVADEngine:
    """VAD-инференс. Параметры (sample_rate/threshold) — из cfg.vad_models."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg = cfg
        self._models: dict[str, tuple[Any, Any]] = {}

    def setup(self, device: str | None) -> None:
        self._device = device or "cpu"

    def _resolve_entry(self, requested_api_model_id: str) -> ProviderLitserveVADModelEntry:
        allowed = allowed_api_model_ids("vad", self._cfg)
        hf = resolve_hf_model_id("vad", requested_api_model_id, self._cfg)
        if hf is None:
            raise ValueError(
                f"VAD: неизвестная модель {requested_api_model_id!r}; доступные: {sorted(allowed)}"
            )
        entry = find_vad_entry(self._cfg, requested_api_model_id)
        if entry is None:
            raise ValueError(
                f"VAD: для api_model_id={requested_api_model_id!r} нет entry в cfg.vad_models"
            )
        return entry

    def _ensure_model(self, entry: ProviderLitserveVADModelEntry) -> tuple[Any, Any]:
        if entry.api_model_id in self._models:
            return self._models[entry.api_model_id]
        try:
            from silero_vad import get_speech_timestamps, load_silero_vad
        except ImportError as exc:
            raise RuntimeError(
                "VAD: установите silero-vad (uv add silero-vad --group rag)"
            ) from exc

        logger.info(
            "Загрузка VAD-модели: api=%s hf=%s", entry.api_model_id, entry.hf_model_id
        )
        started = time.monotonic()
        model = load_silero_vad()
        self._models[entry.api_model_id] = (model, get_speech_timestamps)
        logger.info(
            "VAD-модель %s загружена за %.2fs", entry.api_model_id, time.monotonic() - started
        )
        return self._models[entry.api_model_id]

    def detect_segments(
        self,
        *,
        audio_bytes: bytes,
        api_model_id: str,
        sample_rate_override: int | None,
    ) -> list[dict[str, float]]:
        entry = self._resolve_entry(api_model_id)
        sample_rate = sample_rate_override or entry.sample_rate
        if not sample_rate:
            raise ValueError(
                f"VAD: sample_rate не задан (ни в payload, ни в cfg.vad_models[{api_model_id}].sample_rate)"
            )
        threshold = entry.threshold
        if threshold is None:
            raise ValueError(
                f"VAD: threshold не задан в cfg.vad_models[{api_model_id}].threshold"
            )

        model, get_speech_ts = self._ensure_model(entry)

        n_samples = len(audio_bytes) // 2
        if n_samples == 0:
            return []
        samples = struct.unpack(f"<{n_samples}h", audio_bytes[: n_samples * 2])
        floats = [s / 32768.0 for s in samples]

        import torch
        tensor = torch.tensor(floats, dtype=torch.float32)
        timestamps = get_speech_ts(
            tensor,
            model,
            sampling_rate=sample_rate,
            threshold=threshold,
        )
        result = [
            {
                "start": float(ts["start"]) / sample_rate,
                "end": float(ts["end"]) / sample_rate,
            }
            for ts in timestamps
        ]
        return result
