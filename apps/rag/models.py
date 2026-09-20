"""Контракты HTTP/WS RAG: форма request/response, не близнецы доменных RAG*."""

from __future__ import annotations

from pydantic import Field

from core.models import StrictBaseModel
from core.pagination import ListResponse
from core.rag.models import DocumentProcessingStatus, RAGMetadata, RAGSearchResult


class NamespaceCreateRequest(StrictBaseModel):
    name: str
    description: str | None = None


class NamespaceDeleteResponse(StrictBaseModel):
    success: bool
    name: str


class IngestTextRequest(StrictBaseModel):
    text: str = Field(..., min_length=1)
    document_name: str | None = None
    metadata: RAGMetadata = Field(default_factory=dict)
    document_id: str | None = None


class IndexFileRequest(StrictBaseModel):
    file_id: str = Field(..., min_length=1)
    document_name: str | None = None
    metadata: RAGMetadata = Field(default_factory=dict)


class IndexFileResponse(StrictBaseModel):
    document_id: str
    task_id: str
    status: str
    file_id: str


class DocumentStatusesBatchRequest(StrictBaseModel):
    document_ids: list[str] = Field(..., min_length=1, max_length=500)


class DocumentStatusesBatchResponse(StrictBaseModel):
    statuses: dict[str, DocumentProcessingStatus | None]


class SearchResponse(StrictBaseModel):
    results: list[RAGSearchResult]
    query: str
    namespace_id: str
    provider: str


class GlobalSearchResponse(StrictBaseModel):
    results: dict[str, list[RAGSearchResult]]
    query: str
    provider: str


class ProviderInfo(StrictBaseModel):
    name: str
    enabled: bool
    is_default: bool
    type: str


class ProvidersView(ListResponse[ProviderInfo]):
    current_provider: str


class RagDocumentDeleteResult(StrictBaseModel):
    success: bool
    document_id: str
