"""Движок для локального VAD в provider_litserve.

Список доступных моделей и их параметры (``sample_rate``, ``threshold``)
берутся из ``cfg.vad_models``. Дефолт — ``cfg.vad_default_api_model_id``.

Бэкенд по умолчанию — Silero VAD. При расширении ``cfg.vad_models`` другими
моделями сюда подключаются их адаптеры — диспатч по ``api_model_id``.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import ClassVar, Protocol, TypeAlias, TypedDict

import torch
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from silero_vad import get_speech_timestamps, load_silero_vad

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
from core.models.voice_models import VADSegment
from core.types import JsonValue

logger = get_logger(__name__)

VADRawValue: TypeAlias = JsonValue | bytes | bytearray | memoryview
VADRawBody: TypeAlias = Mapping[str, VADRawValue]


class SileroVADModel(Protocol):
    def reset_states(self) -> None: ...


class SpeechTimestamp(TypedDict):
    start: int
    end: int


class SpeechTimestampGetter(Protocol):
    def __call__(
        self,
        audio: torch.Tensor,
        model: SileroVADModel,
        *,
        sampling_rate: int,
        threshold: float,
    ) -> list[SpeechTimestamp]: ...


class VADDetectionInput(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    audio_bytes: bytes
    model: str
    sample_rate_override: int | None = Field(default=None, gt=0)
    threshold_override: float | None = Field(default=None, ge=0.0, le=1.0)


def _coerce_audio_bytes(raw: VADRawValue | None) -> bytes:
    if raw is None:
        raise HTTPException(status_code=422, detail="VAD: поле audio (или file) обязательно")
    if isinstance(raw, bytes):
        audio_bytes = raw
    elif isinstance(raw, bytearray | memoryview):
        audio_bytes = bytes(raw)
    elif isinstance(raw, list):
        byte_values: list[int] = []
        for item in raw:
            if not isinstance(item, int) or isinstance(item, bool):
                raise HTTPException(status_code=422, detail="VAD: audio должен быть bytes или list[int]")
            byte_values.append(item)
        try:
            audio_bytes = bytes(byte_values)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="VAD: audio содержит байт вне диапазона 0..255") from exc
    else:
        raise HTTPException(status_code=422, detail="VAD: audio должен быть bytes или list[int]")
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=422, detail="VAD: поле audio (или file) обязательно")
    return audio_bytes


def parse_vad_body(
    raw: VADRawBody | Request,
    *,
    default_api_model_id: str,
) -> VADDetectionInput:
    """Разобрать тело VAD-запроса.

    Поля: ``audio`` (PCM bytes) или ``file``, ``model`` (опционально, api id),
    ``sample_rate`` (опционально, переопределяет дефолт модели).
    """
    if isinstance(raw, Request):
        raise HTTPException(status_code=422, detail="VAD: LitServe должен передать подготовленное тело запроса")

    audio_raw = raw.get("audio")
    if audio_raw is None:
        audio_raw = raw.get("file")
    audio_bytes = _coerce_audio_bytes(audio_raw)

    model_raw = raw.get("model")
    if model_raw is None:
        requested_model = ""
    elif isinstance(model_raw, str):
        requested_model = model_raw.strip()
    else:
        raise HTTPException(status_code=422, detail="VAD: model должен быть строкой")
    if requested_model == "":
        requested_model = default_api_model_id.strip()
    if requested_model == "":
        raise HTTPException(
            status_code=422,
            detail="VAD: model обязателен (либо явно, либо vad_default_api_model_id в конфиге)",
        )

    sample_rate_raw = raw.get("sample_rate")
    if sample_rate_raw is None:
        sample_rate_override = None
    elif isinstance(sample_rate_raw, int) and not isinstance(sample_rate_raw, bool):
        sample_rate_override = sample_rate_raw
    else:
        raise HTTPException(status_code=422, detail="VAD: sample_rate должен быть целым числом")

    threshold_raw = raw.get("threshold")
    if threshold_raw is None:
        threshold_override = None
    elif isinstance(threshold_raw, int | float) and not isinstance(threshold_raw, bool):
        threshold_override = float(threshold_raw)
    else:
        raise HTTPException(status_code=422, detail="VAD: threshold должен быть числом")

    return VADDetectionInput(
        audio_bytes=audio_bytes,
        model=requested_model,
        sample_rate_override=sample_rate_override,
        threshold_override=threshold_override,
    )


class LocalVADEngine:
    """VAD-инференс. Параметры (sample_rate/threshold) — из cfg.vad_models."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._models: dict[str, tuple[SileroVADModel, SpeechTimestampGetter]] = {}
        self._device: str = "cpu"

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

    def _ensure_model(self, entry: ProviderLitserveVADModelEntry) -> tuple[SileroVADModel, SpeechTimestampGetter]:
        if entry.api_model_id in self._models:
            return self._models[entry.api_model_id]

        logger.info(
            "Загрузка VAD-модели: api=%s hf=%s", entry.api_model_id, entry.hf_model_id
        )
        started = time.monotonic()
        model = load_silero_vad()
        timestamp_getter = get_speech_timestamps
        self._models[entry.api_model_id] = (model, timestamp_getter)
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
        threshold_override: float | None,
    ) -> list[VADSegment]:
        entry = self._resolve_entry(api_model_id)
        sample_rate = sample_rate_override or entry.sample_rate
        if not sample_rate:
            raise ValueError(
                f"VAD: sample_rate не задан (ни в payload, ни в cfg.vad_models[{api_model_id}].sample_rate)"
            )
        threshold = threshold_override if threshold_override is not None else entry.threshold
        if threshold is None:
            raise ValueError(
                f"VAD: threshold не задан в cfg.vad_models[{api_model_id}].threshold"
            )

        model, get_speech_ts = self._ensure_model(entry)

        n_samples = len(audio_bytes) // 2
        if n_samples == 0:
            return []
        floats = [
            int.from_bytes(audio_bytes[offset : offset + 2], "little", signed=True) / 32768.0
            for offset in range(0, n_samples * 2, 2)
        ]

        tensor = torch.Tensor(floats)
        timestamps = get_speech_ts(
            tensor,
            model,
            sampling_rate=sample_rate,
            threshold=threshold,
        )
        return [
            VADSegment(
                start=float(ts["start"]) / sample_rate,
                end=float(ts["end"]) / sample_rate,
            )
            for ts in timestamps
        ]
