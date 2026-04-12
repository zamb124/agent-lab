"""Инференс реранкера для LitServe и ``apps.provider_litserve.openai_server_contracts``."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException
from pydantic import ValidationError

from core.config.models import ProviderLitserveInfraConfig
from apps.provider_litserve.openai_server_contracts import (
    RerankQueryPassagesRequest,
    placeholder_rerank_scores,
)

Backend = Literal["placeholder", "flagllm"]


def parse_rerank_body(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="Тело запроса: ожидается JSON-объект")
    try:
        b = RerankQueryPassagesRequest.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors()) from e
    return {"model": b.model, "query": b.query, "passages": b.passages}


class LocalRerankerEngine:
    """FlagLLMReranker или placeholder; ответ ``{scores}`` как у ``RerankerHTTPClient``."""

    def __init__(self, cfg: ProviderLitserveInfraConfig) -> None:
        self._cfg = cfg
        self._backend: Backend = "placeholder"
        self._model: Any = None

    def setup(self, device: str | None) -> None:
        self._backend = self._cfg.backend
        if self._backend == "placeholder":
            self._model = None
            return

        mid = self._cfg.model_id
        try:
            from FlagEmbedding import FlagLLMReranker
        except ImportError as e:
            raise RuntimeError(
                "backend=flagllm: установите группу зависимостей uv sync --group reranker-model"
            ) from e
        if not device:
            raise RuntimeError("LitServe: пустой device в setup()")
        cuda = device.startswith("cuda")
        bf16 = self._cfg.use_bf16 and cuda
        fp16 = (not bf16) and cuda and self._cfg.use_fp16
        self._model = FlagLLMReranker(
            mid,
            use_fp16=fp16,
            use_bf16=bf16,
            devices=[device],
            batch_size=self._cfg.model_batch_size,
            max_length=self._cfg.max_length,
            trust_remote_code=True,
            normalize=self._cfg.normalize_scores,
        )

    def allowed_model_ids(self) -> frozenset[str]:
        configured_ids = [model_id.strip() for model_id in self._cfg.rerank_model_ids if model_id.strip()]
        return frozenset(
            {
                self._cfg.rerank_openai_model_id.strip(),
                self._cfg.model_id.strip(),
                *configured_ids,
            }
        )

    def rerank(self, query: str, passages: list[str], requested_model: str | None = None) -> dict[str, Any]:
        if requested_model is not None:
            model_id = requested_model.strip()
            if model_id not in self.allowed_model_ids():
                raise HTTPException(
                    status_code=422,
                    detail={
                        "reason": "unknown_rerank_model",
                        "model": requested_model,
                        "allowed": sorted(self.allowed_model_ids()),
                    },
                )
        if not passages:
            return {"scores": []}
        if len(passages) > self._cfg.max_passages:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "too_many_passages",
                    "max_passages": self._cfg.max_passages,
                    "got": len(passages),
                },
            )
        if len(query) > self._cfg.max_query_chars:
            raise HTTPException(
                status_code=422,
                detail={
                    "reason": "query_too_long",
                    "max_chars": self._cfg.max_query_chars,
                    "got": len(query),
                },
            )
        for i, p in enumerate(passages):
            if len(p) > self._cfg.max_passage_chars:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "reason": "passage_too_long",
                        "index": i,
                        "max_chars": self._cfg.max_passage_chars,
                        "got": len(p),
                    },
                )

        if self._backend == "placeholder":
            return {"scores": placeholder_rerank_scores(query, passages)}

        if self._model is None:
            raise HTTPException(status_code=503, detail={"reason": "reranker_not_initialized"})
        pairs = [(query, p) for p in passages]
        raw = self._model.compute_score(
            pairs,
            batch_size=self._cfg.model_batch_size,
            max_length=self._cfg.max_length,
        )
        if not isinstance(raw, list):
            raw = list(raw)
        scores = [float(s) for s in raw]
        if len(scores) != len(passages):
            raise HTTPException(
                status_code=503,
                detail={"reason": "scores_length_mismatch", "expected": len(passages), "got": len(scores)},
            )
        return {"scores": scores}
