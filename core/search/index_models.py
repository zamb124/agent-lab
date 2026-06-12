"""Platform search index registry contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from core.models import StrictBaseModel


class SearchIndexRetrievalConfig(StrictBaseModel):
    semantic: bool = True
    lexical: bool = True
    rerank: bool = True
    rrf_k: int | None = 60
    per_channel_top_k: int | None = None
    snippet_max_chars: int = Field(default=2000, ge=200, le=8000)


class SearchIndexDefinition(StrictBaseModel):
    search_index_id: str
    company_id: str
    display_name: str
    description: str | None = None
    rag_namespace_id: str
    rag_collection_id: str
    enabled: bool
    search_enabled: bool
    retrieval: SearchIndexRetrievalConfig
    indexing_profile_key: str | None = None
    created_at: datetime
    updated_at: datetime


class SearchIndexCreateRequest(StrictBaseModel):
    search_index_id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=512)
    description: str | None = None
    rag_namespace_id: str = Field(..., min_length=1, max_length=255)
    rag_collection_id: str = Field(..., min_length=1, max_length=128)
    search_enabled: bool = True
    retrieval: SearchIndexRetrievalConfig = Field(default_factory=SearchIndexRetrievalConfig)
    indexing_profile_key: str | None = None


class SearchIndexPatchRequest(StrictBaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = None
    enabled: bool | None = None
    search_enabled: bool | None = None
    retrieval: SearchIndexRetrievalConfig | None = None
    indexing_profile_key: str | None = None


class SearchIndexBatchGetRequest(StrictBaseModel):
    search_index_ids: list[str] = Field(..., min_length=1, max_length=5)
