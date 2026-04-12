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
    embedding_model_ids: list[str],
    embedding_hf_model_id: str,
    embedding_dimension: int,
    embedding_context_length: int,
    rerank_openai_model_id: str,
    rerank_model_ids: list[str],
    rerank_hf_model_id: str,
    rerank_context_length: int,
    chat_model_ids: list[str],
    created: int,
) -> dict[str, Any]:
    """
    Тело GET ``/v1/models`` для провайдера: модели эмбеддингов, реранка и чата,
    те же поля верхнего уровня, что у OpenRouter ``/models``.
    """
    def _uniq(ids: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for model_id in ids:
            normalized = model_id.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    embedding_ids = _uniq([embedding_openai_model_id, *embedding_model_ids])
    rerank_ids = _uniq([rerank_openai_model_id, *rerank_model_ids])
    chat_ids = _uniq(chat_model_ids)

    data: list[dict[str, Any]] = []

    for emb_id in embedding_ids:
        data.append(
            _openrouter_like_model_object(
                model_id=emb_id,
                name=emb_id,
                description=(
                    f"Local embedding model (HF: {embedding_hf_model_id}), "
                    f"vector dimension {embedding_dimension}. "
                    "Use POST /v1/embeddings."
                ),
                created=created,
                context_length=embedding_context_length,
                output_modalities=["embeddings"],
            )
        )

    for rerank_id in rerank_ids:
        data.append(
            _openrouter_like_model_object(
                model_id=rerank_id,
                name=rerank_id,
                description=(
                    f"Local cross-encoder reranker (HF: {rerank_hf_model_id}). "
                    "API: JSON query + passages; response scores[]. "
                    "Use POST /v1/rerank."
                ),
                created=created,
                context_length=rerank_context_length,
                output_modalities=["text"],
            )
        )

    for chat_id in chat_ids:
        data.append(
            _openrouter_like_model_object(
                model_id=chat_id,
                name=chat_id,
                description="OpenAI-compatible chat via POST /v1/chat/completions.",
                created=created,
                context_length=131072,
                output_modalities=["text"],
            )
        )

    return {
        "object": "list",
        "data": data,
    }


class OpenAIEmbeddingsRequest(BaseModel):
    """Тело POST ``/v1/embeddings`` (совместимо с OpenAI)."""

    model_config = ConfigDict(extra="forbid")

    model: str
    input: str | list[str]


class RerankQueryPassagesRequest(BaseModel):
    """Тело POST ``/v1/rerank`` (совпадает с полезной нагрузкой ``RerankerHTTPClient``)."""

    model_config = ConfigDict(extra="forbid")

    model: str | None = None
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
