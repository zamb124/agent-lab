"""REST-зеркало meta-поиска (`search/query/*`)."""

from __future__ import annotations

from fastapi import APIRouter

from apps.search.dependencies import ContainerDep
from apps.search.realtime.operations import (
    op_query_providers_snapshot,
    op_query_search,
    op_query_serp_click,
    op_query_serp_more,
    op_query_serp_refine,
)
from core.context import require_context
from core.search.models import (
    MetaSearchRefineRequest,
    MetaSearchRequest,
    MetaSearchResponse,
    MetaSearchSerpMoreRequest,
    SearchProvidersSnapshot,
    SerpClickEvent,
)
from core.websocket import EmptyPayload

router = APIRouter(tags=["search"])


@router.post("/search", response_model=MetaSearchResponse)
async def meta_search(body: MetaSearchRequest, container: ContainerDep) -> MetaSearchResponse:
    return await op_query_search(body, user=require_context().user, container=container)


@router.post("/search/serp/more", response_model=MetaSearchResponse)
async def meta_search_serp_more(body: MetaSearchSerpMoreRequest, container: ContainerDep) -> MetaSearchResponse:
    return await op_query_serp_more(body, user=require_context().user, container=container)


@router.post("/search/serp/refine", response_model=MetaSearchResponse)
async def meta_search_serp_refine(body: MetaSearchRefineRequest, container: ContainerDep) -> MetaSearchResponse:
    return await op_query_serp_refine(body, user=require_context().user, container=container)


@router.post("/search/serp/click", status_code=204)
async def meta_search_serp_click(body: SerpClickEvent, container: ContainerDep) -> None:
    await op_query_serp_click(body, user=require_context().user, container=container)


@router.get("/providers", response_model=SearchProvidersSnapshot)
async def list_search_providers(container: ContainerDep) -> SearchProvidersSnapshot:
    return await op_query_providers_snapshot(EmptyPayload(), user=require_context().user, container=container)
