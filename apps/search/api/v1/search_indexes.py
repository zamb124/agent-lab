"""REST-зеркало реестра индексов (`search/indexes/*`)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.search.dependencies import ContainerDep
from apps.search.realtime.operations import (
    SearchIndexesListPayload,
    SearchIndexIdPayload,
    SearchIndexUpdatePayload,
    op_indexes_batch_get,
    op_indexes_create,
    op_indexes_get,
    op_indexes_list,
    op_indexes_update,
)
from core.context import require_context
from core.pagination import ListResponse, OffsetPage
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
    return await op_indexes_list(
        SearchIndexesListPayload(limit=limit, offset=offset, enabled=enabled),
        user=require_context().user,
        container=container,
    )


@router.get("/{search_index_id}", response_model=SearchIndexDefinition)
async def get_search_index(search_index_id: str, container: ContainerDep) -> SearchIndexDefinition:
    return await op_indexes_get(
        SearchIndexIdPayload(search_index_id=search_index_id), user=require_context().user, container=container
    )


@router.post("", response_model=SearchIndexDefinition, status_code=201)
async def create_search_index(body: SearchIndexCreateRequest, container: ContainerDep) -> SearchIndexDefinition:
    return await op_indexes_create(body, user=require_context().user, container=container)


@router.patch("/{search_index_id}", response_model=SearchIndexDefinition)
async def patch_search_index(
    search_index_id: str, body: SearchIndexPatchRequest, container: ContainerDep
) -> SearchIndexDefinition:
    return await op_indexes_update(
        SearchIndexUpdatePayload.model_validate(
            {**body.model_dump(exclude_unset=True), "search_index_id": search_index_id}
        ),
        user=require_context().user,
        container=container,
    )


@router.post("/batch-get", response_model=ListResponse[SearchIndexDefinition])
async def batch_get_search_indexes(
    body: SearchIndexBatchGetRequest, container: ContainerDep
) -> ListResponse[SearchIndexDefinition]:
    return await op_indexes_batch_get(body, user=require_context().user, container=container)
