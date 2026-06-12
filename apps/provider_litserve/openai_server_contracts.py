"""
Тела запросов и формы ответов OpenAI-совместимого HTTP для LitServe ``provider_litserve``.

Клиентский URL реранка: ``core.rag.openai_http_contracts.provider_litserve_rerank_http_url``.
"""

from __future__ import annotations

import time
import uuid
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from apps.provider_litserve.provider_litserve_http_schemas import (
    ChatCompletionChoiceBody,
    ChatCompletionMessageBody,
    EmbeddingDataItem,
    ModelArchitectureSchema,
    ModelPricingSchema,
    OpenAIChatCompletionsResponseBody,
    OpenAIEmbeddingsResponseBody,
    TopProviderSchema,
    V1ModelItemSchema,
    V1ModelsResponseBody,
)


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
    embedding_openai_model_id: str,
    embedding_model_ids: list[str],
    embedding_hf_model_id: str,
    embedding_dimension: int,
    embedding_context_length: int,
    rerank_openai_model_id: str,
    rerank_model_ids: list[str],
    rerank_hf_model_id: str,
    rerank_context_length: int,
    llm_openai_model_id: str | None = None,
    llm_model_ids: list[str] | None = None,
    llm_hf_model_id: str | None = None,
    llm_context_length: int = 32768,
    stt_model_ids: list[str],
    tts_model_ids: list[str],
    vad_model_ids: list[str],
    created: int,
) -> V1ModelsResponseBody:
    """
    Тело GET ``/v1/models`` для провайдера: модели эмбеддингов, реранка и речи,
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
    stt_ids = _uniq(stt_model_ids)
    tts_ids = _uniq(tts_model_ids)
    vad_ids = _uniq(vad_model_ids)

    data: list[V1ModelItemSchema] = []

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
                capabilities=["embedding"],
                native_dimension=embedding_dimension,
                storage_dimension=embedding_dimension,
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
                capabilities=["rerank"],
            )
        )

    llm_ids = _uniq([*( [llm_openai_model_id] if llm_openai_model_id else []), *(llm_model_ids or [])])
    for llm_id in llm_ids:
        hf_ref = llm_hf_model_id if llm_hf_model_id is not None else llm_id
        data.append(
            _openrouter_like_model_object(
                model_id=llm_id,
                name=llm_id,
                description=(
                    f"Local chat LLM (HF: {hf_ref}). "
                    "Use POST /v1/chat/completions."
                ),
                created=created,
                context_length=llm_context_length,
                output_modalities=["text"],
                capabilities=["llm_chat"],
                supported_parameters=["temperature", "max_tokens", "response_format"],
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


class OpenAIChatMessage(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    role: str
    content: str


class OpenAIChatResponseFormat(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    type: Literal["json_object", "text"]


class OpenAIChatCompletionsRequest(BaseModel):
    """Тело POST ``/v1/chat/completions`` (совместимо с OpenAI)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    model: str
    messages: list[OpenAIChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    response_format: OpenAIChatResponseFormat | None = None


def build_openai_chat_completions_response(
    *,
    model_id: str,
    content: str,
) -> OpenAIChatCompletionsResponseBody:
    return OpenAIChatCompletionsResponseBody(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=model_id,
        choices=[
            ChatCompletionChoiceBody(
                message=ChatCompletionMessageBody(content=content),
            )
        ],
    )


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
