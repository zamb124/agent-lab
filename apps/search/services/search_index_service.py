"""Реестр индексов поиска."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from apps.search.errors import SearchIndexNotFoundError, SearchIndexSearchDisabledError
from core.clients.rag_client import RagClient
from core.search.index_models import (
    SearchIndexCreateRequest,
    SearchIndexDefinition,
    SearchIndexPatchRequest,
)

_SEARCH_INDEX_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def _slug(search_index_id: str) -> str:
    slug = search_index_id.strip().lower()
    if not _SEARCH_INDEX_ID_RE.match(slug):
        raise ValueError(f"invalid search_index_id: {search_index_id}")
    return slug


class SearchIndexService:
    def __init__(self, rag_client: RagClient) -> None:
        self._rag_client: RagClient = rag_client

    async def get(self, search_index_id: str, *, company_id: str) -> SearchIndexDefinition:
        slug = _slug(search_index_id)
        row = await SearchIndexDefinition.by_search_index_id(company_id, slug)
        if row is None:
            raise SearchIndexNotFoundError(slug)
        return row

    async def create(self, body: SearchIndexCreateRequest) -> SearchIndexDefinition:
        slug = _slug(body.search_index_id)
        now = datetime.now(UTC)
        retrieval = body.retrieval
        row = SearchIndexDefinition(
            search_index_id=slug,
            company_id="system",
            display_name=body.display_name,
            description=body.description,
            rag_namespace_id=body.rag_namespace_id,
            rag_collection_id=body.rag_collection_id,
            search_enabled=body.search_enabled,
            retrieval_semantic=retrieval.semantic,
            retrieval_lexical=retrieval.lexical,
            retrieval_rerank=retrieval.rerank,
            retrieval_rerank_max_candidates=retrieval.rerank_max_candidates,
            retrieval_rrf_k=retrieval.rrf_k,
            retrieval_per_channel_top_k=retrieval.per_channel_top_k,
            retrieval_freshness_weight=retrieval.freshness_weight,
            retrieval_freshness_half_life_days=retrieval.freshness_half_life_days,
            retrieval_freshness_recency_half_life_days=retrieval.freshness_recency_half_life_days,
            retrieval_domain_authority_weight=retrieval.domain_authority_weight,
            snippet_max_chars=retrieval.snippet_max_chars,
            indexing_profile_key=body.indexing_profile_key,
            created_at=now,
            updated_at=now,
        )
        stored = await SearchIndexDefinition.create(row)
        _ = await self._rag_client.create_namespace(
            stored.rag_namespace_id,
            description=stored.description or stored.display_name,
        )
        return stored

    async def patch(self, search_index_id: str, body: SearchIndexPatchRequest) -> SearchIndexDefinition:
        row = await self.get(search_index_id, company_id="system")
        if body.display_name is not None:
            row.display_name = body.display_name
        if body.description is not None:
            row.description = body.description
        if body.enabled is not None:
            row.enabled = body.enabled
        if body.search_enabled is not None:
            row.search_enabled = body.search_enabled
        if body.indexing_profile_key is not None:
            row.indexing_profile_key = body.indexing_profile_key
        if body.retrieval is not None:
            retrieval = body.retrieval
            row.retrieval_semantic = retrieval.semantic
            row.retrieval_lexical = retrieval.lexical
            row.retrieval_rerank = retrieval.rerank
            row.retrieval_rerank_max_candidates = retrieval.rerank_max_candidates
            row.retrieval_rrf_k = retrieval.rrf_k
            row.retrieval_per_channel_top_k = retrieval.per_channel_top_k
            row.retrieval_freshness_weight = retrieval.freshness_weight
            row.retrieval_freshness_half_life_days = retrieval.freshness_half_life_days
            row.retrieval_freshness_recency_half_life_days = retrieval.freshness_recency_half_life_days
            row.retrieval_domain_authority_weight = retrieval.domain_authority_weight
            row.snippet_max_chars = retrieval.snippet_max_chars
        row.updated_at = datetime.now(UTC)
        _ = await row.save()
        return row

    async def batch_get(self, search_index_ids: list[str]) -> list[SearchIndexDefinition]:
        return await self.batch_get_for_company(search_index_ids, company_id="system")

    async def batch_get_for_company(
        self, search_index_ids: list[str], *, company_id: str
    ) -> list[SearchIndexDefinition]:
        if len(search_index_ids) == 0:
            return []
        slugs = [_slug(item) for item in search_index_ids]
        rows = await SearchIndexDefinition.list_unordered_by_ids_for_company(slugs, company_id=company_id)
        by_id = {row.search_index_id: row for row in rows}
        missing = [slug for slug in slugs if slug not in by_id]
        if len(missing) > 0:
            raise SearchIndexNotFoundError(missing[0])
        return [by_id[slug] for slug in slugs]

    async def batch_get_search_enabled(
        self,
        search_index_ids: list[str],
        *,
        company_id: str,
    ) -> list[SearchIndexDefinition]:
        rows = await self.batch_get_for_company(search_index_ids, company_id=company_id)
        for row in rows:
            if not row.enabled:
                raise SearchIndexNotFoundError(row.search_index_id)
            if not row.search_enabled:
                raise SearchIndexSearchDisabledError(row.search_index_id)
        return rows
