"""Инференс эмбеддера для LitServe и ``apps.provider_litserve.openai_server_contracts``."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Literal, Protocol

import torch
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sentence_transformers import SentenceTransformer

from apps.provider_litserve.openai_server_contracts import (
    OpenAIEmbeddingsRequest,
    build_openai_embeddings_response,
    normalize_embedding_inputs,
)
from apps.provider_litserve.provider_litserve_http_schemas import OpenAIEmbeddingsResponseBody
from apps.provider_litserve.runtime_models import allowed_api_model_ids, resolve_hf_model_id
from core.config.models import ProviderLitserveInfraConfig
from core.logging import get_logger
from core.types import JsonValue

logger = get_logger(__name__)


class EmbeddingVector(Protocol):
    def __iter__(self) -> Iterator[float]: ...


class EmbeddingMatrix(Protocol):
    shape: tuple[int, ...]

    def __getitem__(self, index: int) -> EmbeddingVector: ...


class SentenceEmbeddingModel(Protocol):
    def encode(self, texts: list[str], *, normalize_embeddings: bool) -> EmbeddingMatrix: ...


def _require_cuda_when_selected(device: str) -> None:
    if not device.startswith("cuda"):
        return
    if not torch.cuda.is_available():
        message = (
            "provider_litserve: CUDA device для эмбеддера недоступен (torch.cuda.is_available() == False); "
            + "нужны драйвер NVIDIA на хосте, NVIDIA Container Toolkit и resources.limits.nvidia.com/gpu в Helm-чарте (deploy/helm/agent-lab/templates/50-gpu/litserve.yaml)."
        )
        raise RuntimeError(message)


def parse_embedding_body(raw: BaseModel | JsonValue) -> OpenAIEmbeddingsRequest:
    if isinstance(raw, BaseModel):
        raw_payload = raw.model_dump(exclude_none=True)
    else:
        raw_payload = raw
    if not isinstance(raw_payload, dict):
        raise HTTPException(status_code=422, detail="Тело запроса: ожидается JSON-объект")
    try:
        body = OpenAIEmbeddingsRequest.model_validate(raw_payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e
    return body


class LocalEmbeddingEngine:
    """SentenceTransformer; ответ совпадает с тем, что парсит ``EmbeddingService``."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._models: dict[str, SentenceEmbeddingModel] = {}
        self._device: str = "cpu"

    def setup(self, device: str | None) -> None:
        """Запоминает устройство для последующей загрузки модели."""
        if device:
            self._device = device

    def _ensure_model(self, hf_model_id: str) -> SentenceEmbeddingModel:
        if hf_model_id in self._models:
            return self._models[hf_model_id]
        _require_cuda_when_selected(self._device)
        use_bf16 = (
            self._cfg.embedding_use_bf16
            and self._device.startswith("cuda")
            and torch.cuda.is_bf16_supported()
        )
        model_kwargs: dict[str, Literal["bfloat16"]] | None = {"torch_dtype": "bfloat16"} if use_bf16 else None
        logger.info(
            "Loading SentenceTransformer model '%s' on '%s' (bf16=%s)",
            hf_model_id,
            self._device,
            use_bf16,
        )
        started_at = time.monotonic()
        model = SentenceTransformer(
            hf_model_id,
            device=self._device,
            model_kwargs=model_kwargs,
        )
        logger.info("Model '%s' loaded in %.2fs", hf_model_id, time.monotonic() - started_at)
        self._models[hf_model_id] = model
        return model

    def allowed_model_ids(self) -> frozenset[str]:
        return allowed_api_model_ids("embedding", self._cfg)

    def embed(self, requested_model: str, inp: str | list[str]) -> OpenAIEmbeddingsResponseBody:
        rid = requested_model.strip()
        hf_model_id = resolve_hf_model_id("embedding", rid, self._cfg)
        if hf_model_id is None:
            allowed = sorted(self.allowed_model_ids())
            logger.warning(
                "POST /v1/embeddings: unknown_embedding_model request=%r allowed=%s",
                requested_model,
                allowed,
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "unknown_embedding_model",
                    "model": requested_model,
                    "allowed": allowed,
                },
            )
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
        matrix = model.encode(texts, normalize_embeddings=True)
        logger.info(
            "Embedding generated: model='%s', texts=%d, duration=%.2fs",
            canonical,
            len(texts),
            time.monotonic() - started_at,
        )
        if len(matrix.shape) != 2:
            raise TypeError("SentenceTransformer.encode must return a 2D embedding matrix")
        vectors = [[float(value) for value in matrix[i]] for i in range(matrix.shape[0])]
        return build_openai_embeddings_response(model_id=canonical, vectors=vectors)
