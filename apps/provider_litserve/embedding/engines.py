"""Инференс эмбеддера для LitServe и ``apps.provider_litserve.openai_server_contracts``."""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
from fastapi import HTTPException
from pydantic import ValidationError

from core.config.models import ProviderLitserveInfraConfig
from apps.provider_litserve.openai_server_contracts import (
    OpenAIEmbeddingsRequest,
    build_openai_embeddings_response,
    normalize_embedding_inputs,
)
from apps.provider_litserve.runtime_models import allowed_api_model_ids, resolve_hf_model_id

logger = logging.getLogger(__name__)


def parse_embedding_body(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="Тело запроса: ожидается JSON-объект")
    try:
        b = OpenAIEmbeddingsRequest.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e
    return {"model": b.model, "input": b.input}


class LocalEmbeddingEngine:
    """SentenceTransformer; ответ совпадает с тем, что парсит ``EmbeddingService``."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg = cfg
        self._models: dict[str, Any] = {}
        self._device = "cpu"

    def setup(self, device: str | None) -> None:
        """Запоминает устройство для последующей загрузки модели."""
        if device:
            self._device = device

    def _ensure_model(self, hf_model_id: str) -> Any:
        if hf_model_id in self._models:
            return self._models[hf_model_id]
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "Локальный эмбеддер: установите зависимости (uv sync --group reranker-model)"
            ) from e
        logger.info("Loading SentenceTransformer model '%s' on '%s'", hf_model_id, self._device)
        started_at = time.monotonic()
        model = SentenceTransformer(hf_model_id, device=self._device)
        logger.info("Model '%s' loaded in %.2fs", hf_model_id, time.monotonic() - started_at)
        self._models[hf_model_id] = model
        return model

    def allowed_model_ids(self) -> frozenset[str]:
        return allowed_api_model_ids("embedding", self._cfg)

    def embed(self, requested_model: str, inp: str | list[str]) -> dict[str, Any]:
        rid = requested_model.strip()
        if rid not in self.allowed_model_ids():
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "unknown_embedding_model",
                    "model": requested_model,
                    "allowed": sorted(self.allowed_model_ids()),
                },
            )
        hf_model_id = resolve_hf_model_id("embedding", rid, self._cfg)
        if hf_model_id is None:
            raise HTTPException(status_code=422, detail={"reason": "unknown_embedding_model", "model": requested_model})
        texts = normalize_embedding_inputs(inp)
        canonical = rid
        if not texts:
            return build_openai_embeddings_response(model_id=canonical, vectors=[])

        max_n = 256
        if len(texts) > max_n:
            raise HTTPException(
                status_code=422,
                detail={"reason": "too_many_inputs", "max": max_n, "got": len(texts)},
            )

        model = self._ensure_model(hf_model_id)
        started_at = time.monotonic()
        raw = model.encode(texts, normalize_embeddings=True)
        logger.info(
            "Embedding generated: model='%s', texts=%d, duration=%.2fs",
            canonical,
            len(texts),
            time.monotonic() - started_at,
        )
        if not isinstance(raw, np.ndarray):
            raw = np.asarray(raw)
        vectors = [raw[i].tolist() for i in range(raw.shape[0])]
        return build_openai_embeddings_response(model_id=canonical, vectors=vectors)
