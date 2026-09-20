"""Поиск wiki: тонкая REST-обвязка того же `op_search_run`."""

from __future__ import annotations

from fastapi import APIRouter

from apps.wiki.dependencies import ContainerDep
from apps.wiki.models.api import WikiSearchRequest
from apps.wiki.models.domain import WikiSearchHit
from apps.wiki.realtime.operations import op_search_run
from core.context import require_context
from core.pagination import ListResponse

router = APIRouter(prefix="/search", tags=["wiki-search"])


@router.post("", response_model=ListResponse[WikiSearchHit])
async def search(
    container: ContainerDep, request: WikiSearchRequest
) -> ListResponse[WikiSearchHit]:
    return await op_search_run(request, user=require_context().user, container=container)
