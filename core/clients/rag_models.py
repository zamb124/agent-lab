"""Pydantic input models for RagClient and Flows RAG tools / code_node SDK."""

from __future__ import annotations

from pydantic import Field

from core.models import StrictBaseModel
from core.rag.models import RAGMetadata, RAGMetadataFilter
from core.rag_indexing_schema import SearchChannelsDefaults


class RagEmptyArgs(StrictBaseModel):
    """No kwargs."""


class RagCreateNamespaceArgs(StrictBaseModel):
    name: str = Field(..., min_length=1, description="Имя нового namespace внутри компании.")
    description: str | None = Field(
        None,
        description="Описание; можно не передавать.",
    )
    provider: str | None = Field(None, description="RAG provider override; опционально.")


class RagAddTextArgs(StrictBaseModel):
    namespace_id: str = Field(..., min_length=1, description="Имя существующего namespace.")
    collection_id: str = Field(
        ...,
        min_length=1,
        description="Подкорпус внутри namespace; кладётся в metadata.collection_id.",
    )
    text: str = Field(..., min_length=1, description="Текст для индексации.")
    document_name: str | None = Field(None, description="Имя документа; опционально.")
    metadata: RAGMetadata | None = Field(
        None,
        description="Метаданные документа (объект JSON); опционально.",
    )
    document_id: str | None = Field(
        None,
        description="Явный id документа для идемпотентной перезаписи; опционально.",
    )
    provider: str | None = Field(None, description="RAG provider override; опционально.")


class RagIndexFileArgs(StrictBaseModel):
    namespace_id: str = Field(..., min_length=1)
    file_id: str = Field(..., min_length=1)
    metadata: RAGMetadata
    document_name: str | None = None
    provider: str | None = None


class RagNamespaceDocumentArgs(StrictBaseModel):
    namespace_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    provider: str | None = None


class RagDeleteNamespaceArgs(StrictBaseModel):
    namespace_id: str = Field(..., min_length=1)
    provider: str | None = None


class RagDocumentIdArgs(StrictBaseModel):
    document_id: str = Field(..., min_length=1)


class RagDocumentIdsArgs(StrictBaseModel):
    document_ids: list[str] = Field(..., min_length=1)


class RagRetrievalOptions(StrictBaseModel):
    channels: SearchChannelsDefaults | None = Field(
        None,
        description="Каналы гибридного поиска (semantic/lexical); как у REST SearchRequest.",
    )
    rrf_k: int | None = Field(None, ge=1, description="Параметр RRF; опционально.")
    per_channel_top_k: int | None = Field(
        None,
        ge=1,
        description="Верхняя граница кандидатов на канал; опционально.",
    )
    rerank: bool | None = Field(
        None,
        description="Включить пост-retrieval реранк; None — дефолты сервера/профиля.",
    )
    rerank_max_candidates: int | None = Field(
        None,
        ge=1,
        description="Верхняя граница кандидатов, отправляемых в реранкер; опционально.",
    )
    retrieval: bool | None = Field(
        None,
        description="Флаг retrieval в теле поиска; семантика на стороне провайдера.",
    )
    freshness_weight: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Вес freshness decay в итоговом скоре (0..1); None/0 — выключено.",
    )
    freshness_half_life_days: float | None = Field(
        None,
        gt=0.0,
        description="Период полураспада freshness decay в днях; опционально.",
    )


class RagSearchArgs(RagRetrievalOptions):
    namespace_id: str = Field(
        ...,
        min_length=1,
        description="Имя namespace, в который уже загружали документы (как при rag_create_namespace / rag_add_text).",
    )
    collection_id: str = Field(
        ...,
        min_length=1,
        description="Подкорпус; мерджится в filters.collection_id.",
    )
    query: str = Field(
        ...,
        min_length=1,
        description="Запрос естественным языком по смыслу фрагментов в этом namespace.",
    )
    limit: int = Field(5, ge=1, le=100)
    filters: RAGMetadataFilter | None = Field(None, description="Фильтры по metadata; опционально.")
    provider: str | None = Field(None, description="RAG provider override; опционально.")


class RagGlobalSearchArgs(RagRetrievalOptions):
    namespace_ids: list[str] = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    limit: int = Field(5, ge=1, le=100)
    filters: RAGMetadataFilter | None = None
    provider: str | None = None
