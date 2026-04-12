"""
Тела запросов и формы ответов OpenAI-совместимого HTTP для LitServe ``provider_litserve``.

Клиентский URL реранка: ``core.rag.openai_http_contracts.provider_litserve_rerank_http_url``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


def _openrouter_like_model_object(
    *,
    model_id: str,
    name: str,
    description: str,
    created: int,
    context_length: int,
    output_modalities: list[str],
    input_modalities: list[str] | None = None,
) -> dict[str, Any]:
    """Один элемент ``data[]`` для GET ``/v1/models`` (форма как у OpenRouter)."""
    ins = input_modalities if input_modalities is not None else ["text"]
    slug = model_id.replace("/", "-").lower()
    return {
        "id": model_id,
        "canonical_slug": slug,
        "name": name,
        "created": created,
        "description": description,
        "context_length": context_length,
        "architecture": {
            "input_modalities": ins,
            "output_modalities": output_modalities,
        },
        "pricing": {
            "prompt": "0",
            "completion": "0",
            "request": "0",
            "image": "0",
        },
        "top_provider": {
            "name": "humanitec-rag-gateway",
            "is_moderated": False,
        },
        "per_request_limits": None,
        "object": "model",
        "owned_by": "humanitec-rag-gateway",
    }


def build_provider_litserve_v1_models_response(
    *,
    embedding_openai_model_id: str,
    embedding_hf_model_id: str,
    embedding_dimension: int,
    embedding_context_length: int,
    rerank_openai_model_id: str,
    rerank_hf_model_id: str,
    rerank_context_length: int,
    created: int,
) -> dict[str, Any]:
    """
    Тело GET ``/v1/models`` для провайдера: две модели (эмбеддинги и реранк),
    те же поля верхнего уровня, что у OpenRouter ``/models``.
    """
    emb_name = embedding_openai_model_id
    rr_name = rerank_openai_model_id
    return {
        "object": "list",
        "data": [
            _openrouter_like_model_object(
                model_id=embedding_openai_model_id,
                name=emb_name,
                description=(
                    f"Local embedding model (HF: {embedding_hf_model_id}), "
                    f"vector dimension {embedding_dimension}. "
                    "Use POST /v1/embeddings."
                ),
                created=created,
                context_length=embedding_context_length,
                output_modalities=["embeddings"],
            ),
            _openrouter_like_model_object(
                model_id=rerank_openai_model_id,
                name=rr_name,
                description=(
                    f"Local cross-encoder reranker (HF: {rerank_hf_model_id}). "
                    "API: JSON query + passages; response scores[]. "
                    "Use POST /v1/rerank."
                ),
                created=created,
                context_length=rerank_context_length,
                output_modalities=["text"],
            ),
        ],
    }


class OpenAIEmbeddingsRequest(BaseModel):
    """Тело POST ``/v1/embeddings`` (совместимо с OpenAI)."""

    model_config = ConfigDict(extra="forbid")

    model: str
    input: str | list[str]


class RerankQueryPassagesRequest(BaseModel):
    """Тело POST ``/v1/rerank`` (совпадает с полезной нагрузкой ``RerankerHTTPClient``)."""

    model_config = ConfigDict(extra="forbid")

    query: str
    passages: list[str]


def normalize_embedding_inputs(inp: str | list[str]) -> list[str]:
    return [inp] if isinstance(inp, str) else list(inp)


def build_openai_embeddings_response(*, model_id: str, vectors: list[list[float]]) -> dict[str, Any]:
    """Ответ POST ``/v1/embeddings`` (поле ``model`` — канонический id, как в ``EmbeddingService``)."""
    data: list[dict[str, Any]] = [
        {
            "object": "embedding",
            "embedding": row,
            "index": i,
        }
        for i, row in enumerate(vectors)
    ]
    return {
        "object": "list",
        "data": data,
        "model": model_id,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    }


def placeholder_rerank_scores(query: str, passages: list[str]) -> list[float]:
    """Детерминированные скоры для ``provider_litserve.infra.backend=placeholder`` и тестов."""
    q = set(query.lower().split())
    return [float(len(q & set(p.lower().split()))) for p in passages]
