"""Инференс реранкера для LitServe и ``apps.provider_litserve.openai_server_contracts``."""

from __future__ import annotations

from typing import Literal

import torch
from FlagEmbedding import FlagLLMReranker
from pydantic import BaseModel, ValidationError

from apps.provider_litserve.catalog import ModelCatalog
from apps.provider_litserve.openai_server_contracts import (
    RerankQueryPassagesRequest,
    placeholder_rerank_scores,
)
from apps.provider_litserve.provider_litserve_http_schemas import RerankResponseBody
from core.config.models import ProviderLitserveInfraConfig
from core.logging import get_logger
from core.types import JsonObject, JsonValue
from core.websocket import WsCommandError

Backend = Literal["placeholder", "flagllm"]

logger = get_logger(__name__)


def _require_cuda_when_selected(device: str) -> None:
    if not device.startswith("cuda"):
        return
    if not torch.cuda.is_available():
        message = (
            "provider_litserve: CUDA device для реранкера недоступен (torch.cuda.is_available() == False); "
            + "нужны драйвер NVIDIA на хосте, NVIDIA Container Toolkit и resources.limits.nvidia.com/gpu в Helm-чарте (deploy/helm/agent-lab/templates/50-gpu/litserve.yaml)."
        )
        raise RuntimeError(message)


def parse_rerank_body(raw: BaseModel | JsonValue) -> RerankQueryPassagesRequest:
    if isinstance(raw, BaseModel):
        raw_payload = raw.model_dump(exclude_none=True)
    else:
        raw_payload = raw
    if not isinstance(raw_payload, dict):
        raise WsCommandError(
            "unprocessable",
            "Request body: JSON object expected",
            error_code="ws_invalid_payload",
        )
    try:
        body = RerankQueryPassagesRequest.model_validate(raw_payload)
    except ValidationError as e:
        raise WsCommandError(
            "unprocessable",
            "Request body failed validation",
            error_code="ws_invalid_payload",
        ) from e
    return body


class LocalRerankerEngine:
    """FlagLLMReranker или placeholder; ответ ``{scores}`` как у ``AIRerankerHTTPClient``."""

    def __init__(self, cfg: ProviderLitserveInfraConfig, catalog: ModelCatalog) -> None:
        self._cfg: ProviderLitserveInfraConfig = cfg
        self._catalog: ModelCatalog = catalog
        self._backend: Backend = "placeholder"
        self._models: dict[str, FlagLLMReranker] = {}
        self._device: str = "cpu"

    def setup(self, device: str | None) -> None:
        self._backend = self._cfg.backend
        if self._backend == "placeholder":
            self._models = {}
            return
        if not device:
            raise RuntimeError("LitServe: empty device in setup()")
        self._device = device

    def allowed_model_ids(self) -> frozenset[str]:
        return self._catalog.allowed_ids("rerank")

    def _ensure_model(self, hf_model_id: str) -> FlagLLMReranker:
        if hf_model_id in self._models:
            return self._models[hf_model_id]
        cuda = self._device.startswith("cuda")
        _require_cuda_when_selected(self._device)
        bf16 = self._cfg.use_bf16 and cuda
        fp16 = (not bf16) and cuda and self._cfg.use_fp16
        logger.info(
            "provider_litserve.loading.flagllmreranker.fp16.bf16",
            hf_model_id=hf_model_id,
            _device=self._device,
            fp16=fp16,
            bf16=bf16,
        )
        model = FlagLLMReranker(
            hf_model_id,
            use_fp16=fp16,
            use_bf16=bf16,
            devices=[self._device],
            batch_size=self._cfg.model_batch_size,
            max_length=self._cfg.max_length,
            trust_remote_code=True,
            normalize=self._cfg.normalize_scores,
        )
        self._models[hf_model_id] = model
        return model

    def rerank(self, query: str, passages: list[str], requested_model: str | None = None) -> RerankResponseBody:
        canonical_model = requested_model.strip() if requested_model is not None else self._cfg.rerank_openai_model_id
        hf_model_id = self._catalog.hf_model_id("rerank", canonical_model)
        if hf_model_id is None:
            detail: JsonObject = {"reason": "unknown_rerank_model", "model": canonical_model}
            if requested_model is not None:
                detail["allowed"] = sorted(self.allowed_model_ids())
            raise WsCommandError(
                "unprocessable",
                f"Rerank: unknown model {canonical_model!r}",
                error_code="ws_invalid_payload",
                error_params=detail,
            )
        if not passages:
            return RerankResponseBody(scores=[])
        if len(passages) > self._cfg.max_passages:
            raise WsCommandError(
                "unprocessable",
                "Rerank: too many passages",
                error_code="ws_invalid_payload",
                error_params={
                    "reason": "too_many_passages",
                    "max_passages": self._cfg.max_passages,
                    "got": len(passages),
                },
            )
        if len(query) > self._cfg.max_query_chars:
            raise WsCommandError(
                "unprocessable",
                "Rerank: query is too long",
                error_code="ws_invalid_payload",
                error_params={
                    "reason": "query_too_long",
                    "max_chars": self._cfg.max_query_chars,
                    "got": len(query),
                },
            )
        for i, p in enumerate(passages):
            if len(p) > self._cfg.max_passage_chars:
                raise WsCommandError(
                    "unprocessable",
                    "Rerank: passage is too long",
                    error_code="ws_invalid_payload",
                    error_params={
                        "reason": "passage_too_long",
                        "index": i,
                        "max_chars": self._cfg.max_passage_chars,
                        "got": len(p),
                    },
                )

        if self._backend == "placeholder":
            return RerankResponseBody(scores=placeholder_rerank_scores(query, passages))
        model = self._ensure_model(hf_model_id)
        pairs = [(query, p) for p in passages]
        scores = model.compute_score(
            pairs,
            batch_size=self._cfg.model_batch_size,
            max_length=self._cfg.max_length,
        )
        if len(scores) != len(passages):
            raise WsCommandError(
                "unavailable",
                "Rerank scores length does not match passages",
                error_code="unavailable",
                error_params={
                    "reason": "scores_length_mismatch",
                    "expected": len(passages),
                    "got": len(scores),
                },
            )
        return RerankResponseBody(scores=scores)
