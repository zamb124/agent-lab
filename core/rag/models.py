"""Pydantic модели и публичные контракты RAG системы."""

from datetime import datetime
from typing import ClassVar, Literal, NotRequired, TypeAlias, TypedDict

from pydantic import BaseModel, ConfigDict
from pydantic import Field as PydanticField

from core.models import StrictBaseModel
from core.rag_indexing_schema import SearchChannelsDefaults
from core.types import JsonObject

RAGMetadata: TypeAlias = JsonObject
RAGMetadataFilter: TypeAlias = JsonObject


class RAGCleanupNamespaceTaskResult(TypedDict):
    """Результат фоновой очистки namespace."""

    namespace: str
    status: Literal["cleaned", "empty"]


class RAGListedDocumentTaskItem(TypedDict):
    """Документ из фонового списка RAG worker."""

    document_id: str
    document_name: str
    namespace: str
    metadata: RAGMetadata


class RAGReindexDocumentTaskResult(TypedDict):
    """Результат фоновой переиндексации документа."""

    old_document_id: str
    new_document_id: str
    document_name: str
    namespace: str
    status: Literal["reindexed"]


class RAGCleanupExpiredDocumentsTickResult(TypedDict):
    """Результат cron-тика удаления просроченных RAG документов."""

    skipped: bool
    schedule_task_id: str | None
    candidates_total: int
    deleted_documents: int
    failed_documents: int


class RAGReembedTickResult(TypedDict):
    """Результат cron-тика перевекторизации stale chunks."""

    skipped: bool
    schedule_task_id: str
    reembedded: int
    by_company_written: dict[str, int]
    target_embedding_model: NotRequired[str]
    batch_size: NotRequired[int]


class RAGCleanupOrphanCompanyChunksTickResult(TypedDict):
    """Результат cron-тика удаления chunks без company_id."""

    skipped: bool
    schedule_task_id: str
    deleted: int
    batch_size: NotRequired[int]


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


class RAGIngestTextResponse(StrictBaseModel):
    """Ответ синхронной индексации текста в RAG namespace."""

    document_id: str
    document_name: str
    namespace_id: str
    status: str
    provider: str


class RAGDocumentContent(StrictBaseModel):
    """Собранный текст документа из чанков индекса."""

    document_id: str
    document_name: str
    markdown: str
    chunks_count: int
    metadata: RAGMetadata = PydanticField(default_factory=dict)


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
