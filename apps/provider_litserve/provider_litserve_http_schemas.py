"""
HTTP-контракты ``provider_litserve`` для OpenAPI и проверок ответов.

Семантика совпадает с ``openai_server_contracts`` и с тем, что потребляют
``EmbeddingService`` / ``RerankerHTTPClient`` (``core/rag/post_retrieval_rerank.py``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from core.models.voice_models import VADSegment


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


class VADSegmentsResponseBody(BaseModel):
    """Ответ POST ``/v1/audio/vad``."""

    segments: list[VADSegment]


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
    capabilities: list[str] | None = None
    native_dimension: int | None = None
    storage_dimension: int | None = None
    supported_parameters: list[str] | None = None


class V1ModelsResponseBody(BaseModel):
    """Ответ GET ``/v1/models`` (модели эмбеддингов, реранка и речи)."""

    object: Literal["list"] = "list"
    data: list[V1ModelItemSchema]
