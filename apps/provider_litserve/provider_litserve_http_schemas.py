"""
HTTP-контракты ``provider_litserve`` для OpenAPI и проверок ответов.

Семантика совпадает с ``openai_server_contracts`` и с тем, что потребляют
``EmbeddingService`` / ``RerankerHTTPClient`` в ``apps/rag``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EmbeddingDataItem(BaseModel):
    """Элемент ``data[]`` ответа эмбеддингов."""

    object: Literal["embedding"] = "embedding"
    embedding: list[float]
    index: int


class OpenAIEmbeddingsResponseBody(BaseModel):
    """Ответ POST ``/v1/embeddings`` (поле ``model`` — канонический OpenAI-id из infra)."""

    object: Literal["list"] = "list"
    model: str
    data: list[EmbeddingDataItem]
    usage: dict[str, int] = Field(
        default_factory=lambda: {"prompt_tokens": 0, "total_tokens": 0},
        description="Заглушка usage; локальный шлюз токены не считает.",
    )


class RerankResponseBody(BaseModel):
    """Ответ POST ``/v1/rerank`` (как ожидает ``RerankerHTTPClient``)."""

    scores: list[float] = Field(description="Релевантность каждого элемента ``passages`` в том же порядке.")


class ModelArchitectureSchema(BaseModel):
    input_modalities: list[str]
    output_modalities: list[str]


class ModelPricingSchema(BaseModel):
    prompt: str
    completion: str
    request: str
    image: str


class TopProviderSchema(BaseModel):
    name: str
    is_moderated: bool


class V1ModelItemSchema(BaseModel):
    """Один объект в ``data`` для GET ``/v1/models`` (форма как у OpenRouter)."""

    id: str
    canonical_slug: str
    name: str
    created: int
    description: str
    context_length: int
    architecture: ModelArchitectureSchema
    pricing: ModelPricingSchema
    top_provider: TopProviderSchema
    per_request_limits: None = None
    object: Literal["model"] = "model"
    owned_by: str


class V1ModelsResponseBody(BaseModel):
    """Ответ GET ``/v1/models`` (две модели: эмбеддинги и реранк)."""

    object: Literal["list"] = "list"
    data: list[V1ModelItemSchema]


def validate_embeddings_response(payload: dict[str, Any]) -> OpenAIEmbeddingsResponseBody:
    return OpenAIEmbeddingsResponseBody.model_validate(payload)


def validate_rerank_response(payload: dict[str, Any]) -> RerankResponseBody:
    return RerankResponseBody.model_validate(payload)


def validate_v1_models_response(payload: dict[str, Any]) -> V1ModelsResponseBody:
    return V1ModelsResponseBody.model_validate(payload)
