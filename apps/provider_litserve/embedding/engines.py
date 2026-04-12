"""Инференс эмбеддера для LitServe и ``apps.provider_litserve.openai_server_contracts``."""

from __future__ import annotations

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
        self._model: Any = None
        self._device = "cpu"

    def setup(self, device: str | None) -> None:
        """Запоминает устройство; веса подгружаются при первом ``embed`` (startup без sentence-transformers)."""
        if device:
            self._device = device

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        mid = self._cfg.embedding_model_id
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "Локальный эмбеддер: установите зависимости (uv sync --group reranker-model)"
            ) from e
        self._model = SentenceTransformer(mid, device=self._device)

    def allowed_model_ids(self) -> frozenset[str]:
        return frozenset(
            {
                self._cfg.embedding_openai_model_id.strip(),
                self._cfg.embedding_model_id.strip(),
            }
        )

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
        texts = normalize_embedding_inputs(inp)
        canonical = self._cfg.embedding_openai_model_id
        if not texts:
            return build_openai_embeddings_response(model_id=canonical, vectors=[])

        max_n = 256
        if len(texts) > max_n:
            raise HTTPException(
                status_code=422,
                detail={"reason": "too_many_inputs", "max": max_n, "got": len(texts)},
            )

        self._ensure_model()
        raw = self._model.encode(texts, normalize_embeddings=True)
        if not isinstance(raw, np.ndarray):
            raw = np.asarray(raw)
        vectors = [raw[i].tolist() for i in range(raw.shape[0])]
        return build_openai_embeddings_response(model_id=canonical, vectors=vectors)
