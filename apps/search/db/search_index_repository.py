"""Search index registry repository."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import func, select

from apps.search.db.base import SearchDatabase
from apps.search.db.models import SearchIndexRow
from apps.search.errors import SearchIndexNotFoundError, SearchIndexSearchDisabledError
from core.pagination import OffsetPage
from core.search.index_models import (
    SearchIndexCreateRequest,
    SearchIndexDefinition,
    SearchIndexPatchRequest,
    SearchIndexRetrievalConfig,
)

_SEARCH_INDEX_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def search_index_row_to_definition(row: SearchIndexRow) -> SearchIndexDefinition:
    return SearchIndexDefinition(
        search_index_id=row.search_index_id,
        company_id=row.company_id,
        display_name=row.display_name,
        description=row.description,
        rag_namespace_id=row.rag_namespace_id,
        rag_collection_id=row.rag_collection_id,
        enabled=row.enabled,
        search_enabled=row.search_enabled,
        retrieval=SearchIndexRetrievalConfig(
            semantic=row.retrieval_semantic,
            lexical=row.retrieval_lexical,
            rerank=row.retrieval_rerank,
            rrf_k=row.retrieval_rrf_k,
            per_channel_top_k=row.retrieval_per_channel_top_k,
            snippet_max_chars=row.snippet_max_chars,
        ),
        indexing_profile_key=row.indexing_profile_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SearchIndexRepository:
    def __init__(self, db: SearchDatabase) -> None:
        self._db: SearchDatabase = db

    @staticmethod
    def _validate_slug(search_index_id: str) -> str:
        slug = search_index_id.strip().lower()
        if not _SEARCH_INDEX_ID_RE.match(slug):
            raise ValueError(f"invalid search_index_id: {search_index_id}")
        return slug

    async def get(self, search_index_id: str, *, company_id: str) -> SearchIndexDefinition:
        slug = self._validate_slug(search_index_id)
        async with self._db.session() as session:
            stmt = select(SearchIndexRow).where(
                SearchIndexRow.search_index_id == slug,
                SearchIndexRow.company_id == company_id,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
        if row is None:
            raise SearchIndexNotFoundError(slug)
        return search_index_row_to_definition(row)

    async def list_page(
        self,
        *,
        company_id: str,
        enabled: bool | None,
        limit: int,
        offset: int,
    ) -> OffsetPage[SearchIndexDefinition]:
        async with self._db.session() as session:
            base = select(SearchIndexRow).where(SearchIndexRow.company_id == company_id)
            if enabled is not None:
                base = base.where(SearchIndexRow.enabled == enabled)
            count_stmt = select(func.count()).select_from(base.subquery())
            total = int((await session.execute(count_stmt)).scalar_one())
            stmt = base.order_by(SearchIndexRow.search_index_id).limit(limit).offset(offset)
            rows = list((await session.execute(stmt)).scalars().all())
        return OffsetPage[SearchIndexDefinition](
            items=[search_index_row_to_definition(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def create(self, company_id: str, body: SearchIndexCreateRequest) -> SearchIndexDefinition:
        slug = self._validate_slug(body.search_index_id)
        now = datetime.now(UTC)
        row = SearchIndexRow(
            search_index_id=slug,
            company_id=company_id,
            display_name=body.display_name,
            description=body.description,
            rag_namespace_id=body.rag_namespace_id,
            rag_collection_id=body.rag_collection_id,
            enabled=True,
            search_enabled=body.search_enabled,
            retrieval_semantic=body.retrieval.semantic,
            retrieval_lexical=body.retrieval.lexical,
            retrieval_rerank=body.retrieval.rerank,
            retrieval_rrf_k=body.retrieval.rrf_k,
            retrieval_per_channel_top_k=body.retrieval.per_channel_top_k,
            snippet_max_chars=body.retrieval.snippet_max_chars,
            indexing_profile_key=body.indexing_profile_key,
            created_at=now,
            updated_at=now,
        )
        async with self._db.session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return search_index_row_to_definition(row)

    async def patch(
        self,
        search_index_id: str,
        *,
        company_id: str,
        body: SearchIndexPatchRequest,
    ) -> SearchIndexDefinition:
        slug = self._validate_slug(search_index_id)
        async with self._db.session() as session:
            stmt = select(SearchIndexRow).where(
                SearchIndexRow.search_index_id == slug,
                SearchIndexRow.company_id == company_id,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                raise SearchIndexNotFoundError(slug)
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
                row.retrieval_semantic = body.retrieval.semantic
                row.retrieval_lexical = body.retrieval.lexical
                row.retrieval_rerank = body.retrieval.rerank
                row.retrieval_rrf_k = body.retrieval.rrf_k
                row.retrieval_per_channel_top_k = body.retrieval.per_channel_top_k
                row.snippet_max_chars = body.retrieval.snippet_max_chars
            row.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(row)
        return search_index_row_to_definition(row)

    async def batch_get(self, search_index_ids: list[str], *, company_id: str) -> list[SearchIndexDefinition]:
        slugs = [self._validate_slug(item) for item in search_index_ids]
        async with self._db.session() as session:
            stmt = select(SearchIndexRow).where(
                SearchIndexRow.company_id == company_id,
                SearchIndexRow.search_index_id.in_(slugs),
            )
            rows = list((await session.execute(stmt)).scalars().all())
        by_id = {row.search_index_id: search_index_row_to_definition(row) for row in rows}
        missing = [slug for slug in slugs if slug not in by_id]
        if missing:
            raise SearchIndexNotFoundError(missing[0])
        return [by_id[slug] for slug in slugs]

    async def batch_get_search_enabled(
        self,
        search_index_ids: list[str],
        *,
        company_id: str,
    ) -> list[SearchIndexDefinition]:
        definitions = await self.batch_get(search_index_ids, company_id=company_id)
        for definition in definitions:
            if not definition.enabled:
                raise SearchIndexNotFoundError(definition.search_index_id)
            if not definition.search_enabled:
                raise SearchIndexSearchDisabledError(definition.search_index_id)
        return definitions
