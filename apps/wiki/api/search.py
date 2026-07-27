"""
Поиск по wiki: текстовый слой Postgres и смысловой слой RAG.

Режим `auto` сначала спрашивает смысл и добирает текстом: пользователь ищет
формулировкой, а не точным вхождением, но точное вхождение не должно теряться.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from apps.wiki.api._scope import require_scope
from apps.wiki.dependencies import ContainerDep
from apps.wiki.models.api import (
    WikiSearchRequest,
    WikiSearchResponse,
    WikiSearchResultItem,
)
from apps.wiki.models.domain import WikiSearchHit
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/search", tags=["wiki-search"])


def _to_item(hit: WikiSearchHit, channel: str) -> WikiSearchResultItem:
    return WikiSearchResultItem(
        wiki_page_id=hit.wiki_page_id,
        namespace=hit.namespace,
        title=hit.title,
        icon=hit.icon,
        snippet=hit.snippet,
        heading_path=hit.heading_path,
        score=hit.score,
        channel=channel,
        updated_at=hit.updated_at,
    )


@router.post("", response_model=WikiSearchResponse)
async def search(container: ContainerDep, request: WikiSearchRequest) -> WikiSearchResponse:
    scope = await require_scope(container)
    updated_after = (
        datetime.now(timezone.utc) - timedelta(days=request.updated_after_days)
        if request.updated_after_days is not None
        else None
    )

    items: list[WikiSearchResultItem] = []
    seen: set[str] = set()

    if request.mode in ("auto", "semantic"):
        semantic_hits = await container.wiki_service.semantic_search(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            query=request.query,
            limit=request.limit,
            root_page_id=request.root_page_id,
            published_only=request.published_only,
            updated_after=updated_after,
            editor_user_id=request.editor_user_id,
        )
        for hit in semantic_hits:
            seen.add(hit.wiki_page_id)
            items.append(_to_item(hit, "semantic"))

    if request.mode in ("auto", "lexical") and len(items) < request.limit:
        lexical_hits = await container.wiki_service.search_pages(
            company_id=scope.company_id,
            namespace=scope.namespace,
            user_id=scope.user_id,
            query=request.query,
            limit=request.limit,
        )
        for hit in lexical_hits:
            if hit.wiki_page_id in seen:
                continue
            items.append(_to_item(hit, "lexical"))
            if len(items) >= request.limit:
                break

    return WikiSearchResponse(items=items[: request.limit])
