"""История версий страницы: тонкая REST-обвязка тех же `op_*`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.wiki.dependencies import ContainerDep
from apps.wiki.models.api import WikiPageResponse
from apps.wiki.models.domain import WikiRevision, WikiRevisionSummary
from apps.wiki.realtime.operations import (
    WikiRevisionIdPayload,
    WikiRevisionsListPayload,
    op_pages_revisions_list,
    op_revisions_get,
    op_revisions_restore,
)
from core.context import require_context
from core.pagination import ListResponse

router = APIRouter(tags=["wiki-revisions"])


@router.get("/pages/{wiki_page_id}/revisions", response_model=ListResponse[WikiRevisionSummary])
async def list_revisions(
    container: ContainerDep,
    wiki_page_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ListResponse[WikiRevisionSummary]:
    return await op_pages_revisions_list(
        WikiRevisionsListPayload(wiki_page_id=wiki_page_id, limit=limit),
        user=require_context().user,
        container=container,
    )


@router.get("/revisions/{wiki_revision_id}", response_model=WikiRevision)
async def get_revision(container: ContainerDep, wiki_revision_id: str) -> WikiRevision:
    return await op_revisions_get(
        WikiRevisionIdPayload(wiki_revision_id=wiki_revision_id),
        user=require_context().user,
        container=container,
    )


@router.post("/revisions/{wiki_revision_id}/restore", response_model=WikiPageResponse)
async def restore_revision(
    container: ContainerDep, wiki_revision_id: str
) -> WikiPageResponse:
    return await op_revisions_restore(
        WikiRevisionIdPayload(wiki_revision_id=wiki_revision_id),
        user=require_context().user,
        container=container,
    )
