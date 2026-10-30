"""Pydantic модели и публичные контракты RAG системы."""

from typing import Literal, NotRequired, TypeAlias, TypedDict

from pydantic import Field as PydanticField

from core.files.file_ref import FileRef
from core.models import StrictBaseModel
from core.rag_indexing_schema import IndexProfileSplitConfig, SearchChannelsDefaults
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
    rerank_max_candidates: int | None = PydanticField(default=None, gt=0)
    retrieval: bool | None = None
    freshness_weight: float | None = PydanticField(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Вес freshness-канала в гибридном скоринге: доля RRF-score, "
            + "умножаемая на экспоненциальный decay возраста документа. 0/None — выключено."
        ),
    )
    freshness_half_life_days: float | None = PydanticField(
        default=None,
        gt=0.0,
        description="Период полураспада freshness decay в днях.",
    )


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
    split: IndexProfileSplitConfig | None = None


class RAGChunk(StrictBaseModel):
    """Единица retrieval: чанк индекса и поля результата поиска без score."""

    content: str
    document_id: str
    document_name: str
    namespace: str
    chunk_index: int = 0
    total_chunks: int = 1
    page_index: int | None = None
    page_label: str | None = None
    heading_trail: list[str] = PydanticField(default_factory=list)
    files: list[FileRef] = PydanticField(default_factory=list)
    split: IndexProfileSplitConfig = PydanticField(default_factory=IndexProfileSplitConfig)
    attributes: JsonObject = PydanticField(default_factory=dict)


class RAGSearchResult(RAGChunk):
    """Чанк индекса плюс score поиска."""

    score: float
    chunk_id: str
    provenance: JsonObject = PydanticField(default_factory=dict)


class RAGNamespace(StrictBaseModel):
    """Универсальная модель namespace"""

    namespace_id: str
    name: str
    description: str | None = None
    document_count: int = 0
    created_at: str | None = None
    metadata: RAGMetadata = PydanticField(default_factory=dict)


