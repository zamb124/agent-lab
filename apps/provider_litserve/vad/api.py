"""LitServe API для VAD: POST /v1/audio/vad.

Список моделей и их параметры — в ``cfg.vad_models``. Никаких хардкодов.

Аннотация ``request: fastapi.Request`` обязательна для LitServe — см.
комментарий в ``apps/provider_litserve/stt/api.py`` (тот же контракт).

Без ``from __future__ import annotations`` — см. ``stt/api.py``.
"""

from typing import Protocol

import litserve as ls
from fastapi import HTTPException, Request

from apps.provider_litserve.provider_litserve_http_schemas import VADSegmentsResponseBody
from apps.provider_litserve.shared import resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig
from core.models.voice_models import VADSegment
from core.types import JsonValue

from .engines import LocalVADEngine, VADDetectionInput, parse_vad_body


class VADEngine(Protocol):
    def setup(self, device: str | None) -> None: ...

    def detect_segments(
        self,
        *,
        audio_bytes: bytes,
        api_model_id: str,
        sample_rate_override: int | None,
        threshold_override: float | None,
    ) -> list[VADSegment]: ...


class VADLitAPI(ls.LitAPI):
    """Эндпоинт /v1/audio/vad для batch-определения сегментов речи."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/audio/vad")
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._engine: VADEngine = LocalVADEngine(cfg)

    def setup(self, device: str | None) -> None:
        d = device if device is not None else resolve_torch_device(self._cfg)
        self._engine.setup(d)

    def decode_request(self, request: Request, **kwargs: JsonValue) -> VADDetectionInput:
        _ = kwargs
        return parse_vad_body(
            request,
            default_api_model_id=self._cfg.vad_default_api_model_id,
        )

    def predict(self, x: VADDetectionInput, **kwargs: JsonValue) -> list[VADSegment]:
        _ = kwargs
        try:
            return self._engine.detect_segments(
                audio_bytes=x.audio_bytes,
                api_model_id=x.model,
                sample_rate_override=x.sample_rate_override,
                threshold_override=x.threshold_override,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def encode_response(self, output: list[VADSegment], **kwargs: JsonValue) -> VADSegmentsResponseBody:
        _ = kwargs
        return VADSegmentsResponseBody(segments=output)
