"""Platform search index registry contracts."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index
from pydantic import Field, computed_field, field_validator

from core.models import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.pagination import OffsetPage


class SearchIndexRetrievalConfig(StrictBaseModel):
    semantic: bool = True
    lexical: bool = True
    rerank: bool = True
    rerank_max_candidates: int | None = Field(
        default=None,
        gt=0,
        description="Сколько верхних кандидатов после RRF+freshness уходит в reranker.",
    )
    rrf_k: int | None = 60
    per_channel_top_k: int | None = None
    retrieve_limit: int = Field(default=120, ge=10, le=200)
    snippet_max_chars: int = Field(default=2000, ge=200, le=8000)
    freshness_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Вес freshness decay в гибридном скоринге; 0 — выключено.",
    )
    freshness_half_life_days: float = Field(
        default=180.0,
        gt=0.0,
        description="Half-life decay для обычных запросов, в днях.",
    )
    freshness_recency_half_life_days: float = Field(
        default=30.0,
        gt=0.0,
        description="Усиленный half-life для recency-sensitive запросов (новости/годы/«сегодня»).",
    )
    domain_authority_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Вес авторитета домена (Tranco domain_rank): score *= 1 + weight * authority, "
            + "authority = 1 - log10(rank)/6 в [0, 1]. 0 — выключено."
        ),
    )


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


class SearchIndexDefinition(PlatformModel):
    """Реестр индекса. Таблица ``search_indexes``.

    ``retrieval`` — вид для API и рантайма, не колонка. В строке лежат плоские
    ``retrieval_*`` и ``snippet_max_chars``. ``retrieve_limit`` в базе не хранится.
    """

    __database_alias__: ClassVar[str | None] = "search"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "search_indexes"
        unique_together: list[tuple[str, str]] = [
            ("company_id", "rag_namespace_id"),
            ("company_id", "rag_collection_id"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "enabled"]),
        ]

    search_index_id: str = DbField(db_pk=True, max_length=64)
    company_id: str = DbField(max_length=255)
    display_name: str = DbField(max_length=512)
    rag_namespace_id: str = DbField(max_length=255)
    rag_collection_id: str = DbField(max_length=128)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    description: str | None = DbField(default=None, db_type="TEXT")
    enabled: bool = DbField(default=True)
    search_enabled: bool = DbField(default=True)
    retrieval_semantic: bool = DbField(default=True)
    retrieval_lexical: bool = DbField(default=True)
    retrieval_rerank: bool = DbField(default=True)
    retrieval_rerank_max_candidates: int | None = DbField(default=None)
    retrieval_rrf_k: int | None = DbField(default=60)
    retrieval_per_channel_top_k: int | None = DbField(default=None)
    retrieval_freshness_weight: float = DbField(default=0.0)
    retrieval_freshness_half_life_days: float = DbField(default=180.0)
    retrieval_freshness_recency_half_life_days: float = DbField(default=30.0)
    retrieval_domain_authority_weight: float = DbField(default=0.0)
    snippet_max_chars: int = DbField(default=2000)
    indexing_profile_key: str | None = DbField(default=None, max_length=64)

    @computed_field
    @property
    def retrieval(self) -> SearchIndexRetrievalConfig:
        return SearchIndexRetrievalConfig(
            semantic=self.retrieval_semantic,
            lexical=self.retrieval_lexical,
            rerank=self.retrieval_rerank,
            rerank_max_candidates=self.retrieval_rerank_max_candidates,
            rrf_k=self.retrieval_rrf_k,
            per_channel_top_k=self.retrieval_per_channel_top_k,
            snippet_max_chars=self.snippet_max_chars,
            freshness_weight=self.retrieval_freshness_weight,
            freshness_half_life_days=self.retrieval_freshness_half_life_days,
            freshness_recency_half_life_days=self.retrieval_freshness_recency_half_life_days,
            domain_authority_weight=self.retrieval_domain_authority_weight,
        )

    @classmethod
    async def by_search_index_id(cls, company_id: str, search_index_id: str) -> Self | None:
        """Строка компании по search_index_id. Нет строки — None. Пустые company_id и search_index_id — ValueError."""
        if company_id == "":
            raise ValueError("company_id cannot be empty.")
        if search_index_id == "":
            raise ValueError("search_index_id cannot be empty.")
        return await cls.objects.filter(
            search_index_id=search_index_id,
            company_id=company_id,
        ).get_or_none()

    @classmethod
    async def page_by_search_index_id_asc(
        cls,
        *,
        company_id: str,
        enabled: bool | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[SearchIndexDefinition]:
        """Страница индексов компании, ORDER BY search_index_id ASC. enabled равный None не фильтрует. total — COUNT этого фильтра. Пустой company_id ValueError не даёт."""
        rows = cls.objects.filter(company_id=company_id)
        if enabled is not None:
            rows = rows.filter(enabled=enabled)
        total = await rows.count()
        items = await rows.order_by("search_index_id").limit(limit).offset(offset).all()
        return OffsetPage[SearchIndexDefinition].model_validate(
            {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    @classmethod
    async def create(cls, row: Self) -> Self:
        return await cls.objects.create(instance=row)

    @classmethod
    async def list_unordered_by_ids_for_company(
        cls,
        search_index_ids: list[str],
        *,
        company_id: str,
    ) -> list[Self]:
        """Индексы компании по id. Порядка нет. Пустой список — []. Отсутствующие id не входят."""
        if len(search_index_ids) == 0:
            return []
        return await cls.objects.filter(
            company_id=company_id,
            search_index_id__in=search_index_ids,
        ).all()


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
