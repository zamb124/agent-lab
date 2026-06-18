"""REST meta search API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from apps.search.config import get_search_settings
from apps.search.dependencies import ContainerDep
from core.context import get_context
from core.search.models import (
    MetaSearchRequest,
    MetaSearchResponse,
    MetaSearchSerpMoreRequest,
    SearchProvidersSnapshot,
)

router = APIRouter(tags=["search"])


@router.post("/search", response_model=MetaSearchResponse)
async def meta_search(body: MetaSearchRequest, container: ContainerDep) -> MetaSearchResponse:
    ctx = get_context()
    company = ctx.active_company if ctx is not None else None
    user_id = ctx.user.user_id if ctx is not None else None
    try:
        return await container.meta_search_service.search(body, company=company, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/search/serp/more", response_model=MetaSearchResponse)
async def meta_search_serp_more(body: MetaSearchSerpMoreRequest, container: ContainerDep) -> MetaSearchResponse:
    try:
        return await container.meta_search_service.serp_more(body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/providers", response_model=SearchProvidersSnapshot)
async def list_search_providers(container: ContainerDep) -> SearchProvidersSnapshot:
    config = get_search_settings().search
    index_page = await container.search_index_repository.list_page(
        company_id="system",
        enabled=True,
        limit=100,
        offset=0,
    )
    return SearchProvidersSnapshot(
        provider_order=list(config.provider_order),
        index_enabled=config.index.enabled,
        default_index_ids=list(config.index.default_index_ids),
        search_index_ids=[item.search_index_id for item in index_page.items if item.search_enabled],
    )
