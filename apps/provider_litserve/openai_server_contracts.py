"""
Тела запросов и формы ответов OpenAI-совместимого HTTP для LitServe ``provider_litserve``.

Клиентский URL реранка: ``core.rag.openai_http_contracts.provider_litserve_rerank_http_url``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from apps.provider_litserve.provider_litserve_http_schemas import (
    EmbeddingDataItem,
    ModelArchitectureSchema,
    ModelPricingSchema,
    OpenAIEmbeddingsResponseBody,
    TopProviderSchema,
    V1ModelItemSchema,
    V1ModelsResponseBody,
)
from core.models.provider_litserve_model import ProviderLitserveModelPair


def _openrouter_like_model_object(
    *,
    model_id: str,
    name: str,
    description: str,
    created: int,
    context_length: int,
    output_modalities: list[str],
    input_modalities: list[str] | None = None,
    capabilities: list[str] | None = None,
    native_dimension: int | None = None,
    storage_dimension: int | None = None,
    supported_parameters: list[str] | None = None,
) -> V1ModelItemSchema:
    """Один элемент ``data[]`` для GET ``/v1/models`` (форма как у OpenRouter)."""
    ins = input_modalities if input_modalities is not None else ["text"]
    slug = model_id.replace("/", "-").lower()
    return V1ModelItemSchema(
        id=model_id,
        canonical_slug=slug,
        name=name,
        created=created,
        description=description,
        context_length=context_length,
        architecture=ModelArchitectureSchema(
            input_modalities=ins,
            output_modalities=output_modalities,
        ),
        pricing=ModelPricingSchema(
            prompt="0",
            completion="0",
            request="0",
            image="0",
        ),
        top_provider=TopProviderSchema(
            name="humanitec-rag-gateway",
            is_moderated=False,
        ),
        per_request_limits=None,
        owned_by="humanitec-rag-gateway",
        capabilities=capabilities,
        native_dimension=native_dimension,
        storage_dimension=storage_dimension,
        supported_parameters=supported_parameters,
    )


def build_provider_litserve_v1_models_response(
    *,
    embedding_entries: Sequence[ProviderLitserveModelPair],
    rerank_entries: Sequence[ProviderLitserveModelPair],
    stt_model_ids: list[str],
    tts_model_ids: list[str],
    vad_model_ids: list[str],
    created: int,
) -> V1ModelsResponseBody:
    """
    Тело GET ``/v1/models`` для провайдера: модели эмбеддингов, реранка и речи,
    те же поля верхнего уровня, что у OpenRouter ``/models``.
    """
    def _uniq(ids: Sequence[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for model_id in ids:
            normalized = model_id.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    stt_ids = _uniq(stt_model_ids)
    tts_ids = _uniq(tts_model_ids)
    vad_ids = _uniq(vad_model_ids)

    data: list[V1ModelItemSchema] = []

    seen_embedding: set[str] = set()
    for entry in embedding_entries:
        emb_id = entry.api_model_id.strip()
        if not emb_id or emb_id in seen_embedding:
            continue
        seen_embedding.add(emb_id)
        dimension_text = (
            f"vector dimension {entry.dimension}. " if entry.dimension is not None else ""
        )
        data.append(
            _openrouter_like_model_object(
                model_id=emb_id,
                name=emb_id,
                description=(
                    f"Local embedding model (HF: {entry.hf_model_id}), "
                    f"{dimension_text}"
                    "Use POST /v1/embeddings."
                ),
                created=created,
                context_length=entry.context_length or 8192,
                output_modalities=["embeddings"],
                capabilities=["embedding"],
                native_dimension=entry.dimension,
                storage_dimension=entry.dimension,
            )
        )

    seen_rerank: set[str] = set()
    for entry in rerank_entries:
        rerank_id = entry.api_model_id.strip()
        if not rerank_id or rerank_id in seen_rerank:
            continue
        seen_rerank.add(rerank_id)
        data.append(
            _openrouter_like_model_object(
                model_id=rerank_id,
                name=rerank_id,
                description=(
                    f"Local cross-encoder reranker (HF: {entry.hf_model_id}). "
                    "API: JSON query + passages; response scores[]. "
                    "Use POST /v1/rerank."
                ),
                created=created,
                context_length=entry.context_length or 8192,
                output_modalities=["text"],
                capabilities=["rerank"],
            )
        )

    for stt_id in stt_ids:
        data.append(
            _openrouter_like_model_object(
                model_id=stt_id,
                name=stt_id,
                description=(
                    "Local STT (speech recognition). "
                    "Use POST /v1/audio/transcriptions."
                ),
                created=created,
                context_length=0,
                input_modalities=["audio"],
                output_modalities=["text"],
                capabilities=["voice_stt"],
            )
        )

    for tts_id in tts_ids:
        data.append(
            _openrouter_like_model_object(
                model_id=tts_id,
                name=tts_id,
                description=(
                    "Local TTS (speech synthesis). Use POST /v1/audio/speech."
                ),
                created=created,
                context_length=0,
                input_modalities=["text"],
                output_modalities=["audio"],
                capabilities=["voice_tts"],
            )
        )

    for vad_id in vad_ids:
        data.append(
            _openrouter_like_model_object(
                model_id=vad_id,
                name=vad_id,
                description=(
                    "Local VAD (voice activity detection). Use POST /v1/audio/vad."
                ),
                created=created,
                context_length=0,
                input_modalities=["audio"],
                output_modalities=["text"],
                capabilities=["voice_vad"],
            )
        )

    return V1ModelsResponseBody(data=data)


class OpenAIEmbeddingsRequest(BaseModel):
    """Тело POST ``/v1/embeddings`` (совместимо с OpenAI)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    model: str
    input: str | list[str]


class RerankQueryPassagesRequest(BaseModel):
    """Тело POST ``/v1/rerank`` (совпадает с полезной нагрузкой ``AIRerankerHTTPClient``)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    model: str | None = None
    query: str
    passages: list[str]


def normalize_embedding_inputs(inp: str | list[str]) -> list[str]:
    return [inp] if isinstance(inp, str) else list(inp)


def build_openai_embeddings_response(*, model_id: str, vectors: list[list[float]]) -> OpenAIEmbeddingsResponseBody:
    """Ответ POST ``/v1/embeddings`` (поле ``model`` — канонический id, как в ``AIEmbeddingClient``)."""
    data = [
        EmbeddingDataItem(
            embedding=row,
            index=i,
        )
        for i, row in enumerate(vectors)
    ]
    return OpenAIEmbeddingsResponseBody(
        data=data,
        model=model_id,
        usage={"prompt_tokens": 0, "total_tokens": 0},
    )


def placeholder_rerank_scores(query: str, passages: list[str]) -> list[float]:
    """Детерминированные скоры для ``provider_litserve.infra.backend=placeholder`` и тестов."""
    q = set(query.lower().split())
    return [float(len(q & set(p.lower().split()))) for p in passages]
