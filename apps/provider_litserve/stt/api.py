"""LitServe API для STT: POST /v1/audio/transcriptions (OpenAI-совместимое).

Список моделей и их параметры берутся из ``cfg.stt_models`` (никаких
хардкодов в этом модуле). Поддерживает динамический батчинг через
``decode_request`` / ``batch`` / ``predict`` / ``unbatch``.

Аннотация ``request: fastapi.Request`` — обязательное условие LitServe
(`litserve.server.LitAPIRequestHandler._prepare_request`). При этом
аннотации LitServe сам читает body вручную: для ``application/json`` —
``await request.json()``, для ``multipart/form-data`` —
``await request.form()`` — и в ``decode_request`` уже приходит готовый
``dict``. Любая другая аннотация (`Any`, отсутствие) приводит к тому,
что FastAPI пытается вытащить ``request`` как обычный параметр и
отвечает ``422 Unprocessable Content`` до вызова ``decode_request``.

Формат ответа: ``{"text": "распознанный текст"}``.

Без ``from __future__ import annotations``: LitServe сравнивает аннотацию
параметра ``request`` с ``fastapi.Request`` через ``inspect.signature``. При
отложенных аннотациях это строка ``'Request'`` — совпадения нет, в
multiprocessing-queue уходит сырой ASGI-``Request`` (не pickle → 500 /
``Can't get local object 'FastAPI.setup.<locals>.openapi'``).
"""

from typing import Any

import litserve as ls
from fastapi import Request

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

    def decode_request(self, request: Request, **kwargs: Any) -> dict[str, Any]:
        return parse_stt_body(request, default_api_model_id=self._cfg.stt_default_api_model_id)

    def batch(self, inputs: list[Any]) -> list[Any]:
        return inputs

    def predict(self, x: Any, **kwargs: Any) -> list[str]:
        """LitServe: в single-loop в ``predict`` приходит **один** decoded-dict; в batched-loop — ``list[dict]`` после ``batch()``."""
        items: list[dict[str, Any]] = x if isinstance(x, list) else [x]
        return self._engine.transcribe_batch(items)

    def unbatch(self, output: list[Any]) -> Any:
        return output

    def encode_response(self, output: Any, **kwargs: Any) -> dict[str, Any]:
        if isinstance(output, list):
            text = output[0] if output else ""
        else:
            text = str(output)
        return {"text": text}
