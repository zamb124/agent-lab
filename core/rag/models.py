"""Pydantic модели и публичные контракты RAG системы."""

from datetime import datetime
from typing import ClassVar, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

from core.models import StrictBaseModel
from core.rag_indexing_schema import SearchChannelsDefaults
from core.types import JsonObject

RAGMetadata: TypeAlias = JsonObject
RAGMetadataFilter: TypeAlias = JsonObject


class RAGSearchOptions(StrictBaseModel):
    """Опции retrieval-поиска, общие для API, HTTP client, repository и provider."""

    channels: SearchChannelsDefaults | None = None
    rrf_k: int | None = PydanticField(default=None, gt=0)
    per_channel_top_k: int | None = PydanticField(default=None, gt=0)
    rerank: bool | None = None
    retrieval: bool | None = None


class RAGNamespaceSearchRequest(RAGSearchOptions):
    """Тело поиска внутри одного RAG namespace."""

    query: str
    limit: int = PydanticField(default=5, ge=1)
    filters: RAGMetadataFilter | None = None


class RAGGlobalSearchRequest(RAGNamespaceSearchRequest):
    """Тело поиска по нескольким RAG namespace."""

    namespace_ids: list[str]


class RAGDocument(StrictBaseModel):
    """Универсальная модель документа для RAG"""

    document_id: str
    name: str
    namespace: str
    content: str | None = None
    metadata: RAGMetadata = PydanticField(default_factory=dict)
    status: str = "processing"
    created_at: str | None = None
    chunks_count: int | None = None
    indexing_runs: int | None = None
    reindex_count: int | None = None
    split: RAGMetadata | None = None


class RAGSearchResult(StrictBaseModel):
    """Универсальная модель результата поиска"""

    content: str
    score: float
    document_id: str
    document_name: str
    metadata: RAGMetadata = PydanticField(default_factory=dict)
    namespace: str
    chunk_id: str | None = None
    provenance: RAGMetadata = PydanticField(default_factory=dict)


class RAGNamespace(StrictBaseModel):
    """Универсальная модель namespace"""

    namespace_id: str
    name: str
    description: str | None = None
    document_count: int = 0
    created_at: str | None = None
    metadata: RAGMetadata = PydanticField(default_factory=dict)


class FlowRAGConfig(StrictBaseModel):
    """Конфигурация RAG для flow"""

    enabled: bool = False

    namespace_scope: Literal["flow", "company", "session"] = PydanticField(
        default="flow",
        title="Скоуп хранения",
        description="Где хранить документы: company (общие), flow (для этого flow), session (для сессии)",
    )

    search_scopes: list[Literal["flow", "company", "session"]] = PydanticField(
        default_factory=lambda: ["flow"],
        title="Скоупы поиска",
        description="Где искать документы при запросах",
    )

    auto_index_messages: bool = PydanticField(
        default=False,
        title="Автоматическая индексация",
        description="Автоматически индексировать сообщения из сессии",
    )


class DocumentProcessingStatus(BaseModel):
    """
    Статус обработки документа в RAG.

    Статусы:
    - pending: документ принят, ожидает обработки
    - processing: документ обрабатывается (парсинг, chunking, индексация)
    - completed: документ успешно проиндексирован
    - failed: ошибка при обработке

    Первичный ключ в БД — document_id (одна строка на документ).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True, populate_by_name=True)

    document_id: str
    task_id: str
    namespace_id: str
    document_name: str
    status: Literal["pending", "processing", "completed", "failed"]
    error_message: str | None = None
    s3_key: str | None = None
    s3_bucket: str | None = None
    file_size: int | None = None
    chunks_count: int | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    extra_metadata: RAGMetadata | None = None
    ttl_seconds: int = 864000
