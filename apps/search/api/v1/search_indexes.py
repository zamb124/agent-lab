"""Search index registry REST API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.search.dependencies import ContainerDep
from apps.search.errors import SearchIndexNotFoundError
from core.pagination import OffsetPage
from core.search.index_models import (
    SearchIndexBatchGetRequest,
    SearchIndexCreateRequest,
    SearchIndexDefinition,
    SearchIndexPatchRequest,
)

router = APIRouter(prefix="/search-indexes", tags=["search-indexes"])


@router.get("", response_model=OffsetPage[SearchIndexDefinition])
async def list_search_indexes(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    enabled: Annotated[bool | None, Query()] = None,
) -> OffsetPage[SearchIndexDefinition]:
    return await container.search_index_repository.list_page(
        company_id="system",
        enabled=enabled,
        limit=limit,
        offset=offset,
    )


@router.get("/{search_index_id}", response_model=SearchIndexDefinition)
async def get_search_index(search_index_id: str, container: ContainerDep) -> SearchIndexDefinition:
    try:
        return await container.search_index_repository.get(search_index_id, company_id="system")
    except SearchIndexNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=SearchIndexDefinition, status_code=201)
async def create_search_index(
    body: SearchIndexCreateRequest,
    container: ContainerDep,
) -> SearchIndexDefinition:
    try:
        return await container.search_index_service.create(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{search_index_id}", response_model=SearchIndexDefinition)
async def patch_search_index(
    search_index_id: str,
    body: SearchIndexPatchRequest,
    container: ContainerDep,
) -> SearchIndexDefinition:
    try:
        return await container.search_index_service.patch(search_index_id, body)
    except SearchIndexNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/batch-get", response_model=list[SearchIndexDefinition])
async def batch_get_search_indexes(
    body: SearchIndexBatchGetRequest,
    container: ContainerDep,
) -> list[SearchIndexDefinition]:
    try:
        return await container.search_index_service.batch_get(body.search_index_ids)
    except SearchIndexNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
