"""LitServe API для STT: POST /v1/audio/transcriptions (OpenAI-совместимое).

Список моделей и их параметры берутся из ``cfg.stt_models`` (никаких
хардкодов в этом модуле). Поддерживает динамический батчинг через
``decode_request`` / ``batch`` / ``predict`` / ``unbatch``.

Формат ответа: ``{"text": "распознанный текст"}``.
"""

from __future__ import annotations

from typing import Any

import litserve as ls

from apps.provider_litserve.shared import resolve_torch_device
from core.config.models import ProviderLitserveInfraConfig

from .engines import LocalSTTEngine, parse_stt_body


class STTLitAPI(ls.LitAPI):
    """OpenAI-совместимый эндпоинт /v1/audio/transcriptions."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        super().__init__(api_path="/v1/audio/transcriptions")
        self._cfg = cfg
        self._engine = LocalSTTEngine(cfg)

    def setup(self, device: str | None) -> None:
        d = device if device is not None else resolve_torch_device(self._cfg)
        self._engine.setup(d)

    def decode_request(self, request: Any, **kwargs: Any) -> dict[str, Any]:
        return parse_stt_body(request, default_api_model_id=self._cfg.stt_default_api_model_id)

    def batch(self, inputs: list[Any]) -> list[Any]:
        return inputs

    def predict(self, batch: list[Any], **kwargs: Any) -> list[str]:
        return self._engine.transcribe_batch(batch)

    def unbatch(self, outputs: list[Any]) -> Any:
        return outputs

    def encode_response(self, output: Any, **kwargs: Any) -> dict[str, Any]:
        if isinstance(output, list):
            text = output[0] if output else ""
        else:
            text = str(output)
        return {"text": text}
