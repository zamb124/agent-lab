"""LitServe API для TTS: POST /v1/audio/speech (OpenAI-совместимое).

Список моделей и их параметры (lang/voice/sample_rate) — в ``cfg.tts_models``.
Никаких хардкодов в этом модуле.

Аннотация ``request: fastapi.Request`` обязательна для LitServe — см.
комментарий в ``apps/provider_litserve/stt/api.py`` (тот же контракт).

Без ``from __future__ import annotations`` — см. ``stt/api.py``
(совпадение аннотации с ``Request`` для LitServe / pickle).
"""

from typing import Any

import litserve as ls
from fastapi import HTTPException, Request

from apps.provider_litserve.shared import resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig

from .engines import LocalTTSEngine, parse_tts_body


class TTSLitAPI(ls.LitAPI):
    """OpenAI-совместимый эндпоинт /v1/audio/speech."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/audio/speech")
        self._cfg = cfg
        self._engine = LocalTTSEngine(cfg)

    def setup(self, device: str | None) -> None:
        d = device if device is not None else resolve_torch_device(self._cfg)
        self._engine.setup(d)

    def decode_request(self, request: Request, **kwargs: Any) -> dict[str, Any]:
        try:
            return parse_tts_body(
                request,
                default_api_model_id=self._cfg.tts_default_api_model_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def predict(self, x: dict[str, Any], **kwargs: Any) -> bytes:
        try:
            return self._engine.synthesize(
                text=x["text"],
                api_model_id=x["model"],
                voice_override=x.get("voice_override"),
                response_format=x.get("response_format", "wav"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    def encode_response(self, output: Any, **kwargs: Any) -> bytes:
        if isinstance(output, bytes):
            return output
        raise HTTPException(status_code=500, detail="TTS: неожиданный тип ответа")
