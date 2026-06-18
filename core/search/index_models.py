"""Platform search index registry contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from core.models import StrictBaseModel


class SearchIndexRetrievalConfig(StrictBaseModel):
    semantic: bool = True
    lexical: bool = True
    rerank: bool = True
    rrf_k: int | None = 60
    per_channel_top_k: int | None = None
    retrieve_limit: int = Field(default=120, ge=10, le=200)
    snippet_max_chars: int = Field(default=2000, ge=200, le=8000)


class SearchIndexCrawlTaxonomy(StrictBaseModel):
    primary_topics: list[str] = Field(..., min_length=1)
    topic_tags: list[str] = Field(..., min_length=1)
    category_paths: list[list[str]] = Field(default_factory=list)

    @field_validator("primary_topics", "topic_tags")
    @classmethod
    def _validate_slug_tokens(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            token = value.strip().lower()
            if not token:
                raise ValueError("taxonomy token must not be empty")
            if token not in normalized:
                normalized.append(token)
        if not normalized:
            raise ValueError("taxonomy list must not be empty")
        return normalized

    @field_validator("category_paths")
    @classmethod
    def _validate_category_paths(cls, values: list[list[str]]) -> list[list[str]]:
        normalized_paths: list[list[str]] = []
        for path in values:
            if not path:
                raise ValueError("category_path entry must not be empty")
            if len(path) > 3:
                raise ValueError("category_path entry must have at most 3 levels")
            normalized = [segment.strip().lower() for segment in path if segment.strip()]
            if not normalized:
                raise ValueError("category_path entry must not be empty")
            if normalized not in normalized_paths:
                normalized_paths.append(normalized)
        return normalized_paths


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
