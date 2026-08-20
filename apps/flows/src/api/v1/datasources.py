"""HTTP: company datasource connections and protocol (introspect/query/execute)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.flows.src.dependencies import ContainerDep
from core.datasources.models import (
    DatasourceConnection,
    DatasourceConnectionCreate,
    DatasourceConnectionPatch,
    DatasourceConnectorSpec,
    DatasourceConnectorUpsert,
    DatasourceExecuteRequest,
    DatasourceExecuteResult,
    DatasourceQueryRequest,
    DatasourceQueryResult,
    DatasourceSchemaSnapshot,
    DatasourceTestResult,
)
from core.pagination import ListResponse, OffsetPage

router = APIRouter(tags=["datasources"])


def _http_400(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/datasources/connectors", response_model=ListResponse[DatasourceConnectorSpec])
async def list_datasource_connectors(
    container: ContainerDep,
) -> ListResponse[DatasourceConnectorSpec]:
    try:
        items = await container.datasource_service.list_connectors()
    except ValueError as exc:
        raise _http_400(exc) from exc
    return ListResponse[DatasourceConnectorSpec](items=items)


@router.put("/datasources/connectors", response_model=DatasourceConnectorSpec)
async def upsert_datasource_connector(
    body: DatasourceConnectorUpsert,
    container: ContainerDep,
) -> DatasourceConnectorSpec:
    try:
        return await container.datasource_service.upsert_connector(body)
    except ValueError as exc:
        raise _http_400(exc) from exc


@router.get("/datasources", response_model=OffsetPage[DatasourceConnection])
async def list_datasources(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[DatasourceConnection]:
    try:
        items = await container.datasource_service.list_connections()
    except ValueError as exc:
        raise _http_400(exc) from exc
    total = len(items)
    return OffsetPage[DatasourceConnection](
        items=items[offset : offset + limit],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/datasources", response_model=DatasourceConnection)
async def create_datasource(
    body: DatasourceConnectionCreate,
    container: ContainerDep,
) -> DatasourceConnection:
    try:
        return await container.datasource_service.create_connection(body)
    except ValueError as exc:
        raise _http_400(exc) from exc


@router.get("/datasources/{datasource_id}", response_model=DatasourceConnection)
async def get_datasource(
    datasource_id: str,
    container: ContainerDep,
) -> DatasourceConnection:
    try:
        return await container.datasource_service.get_connection(datasource_id)
    except ValueError as exc:
        raise _http_400(exc) from exc


@router.patch("/datasources/{datasource_id}", response_model=DatasourceConnection)
async def patch_datasource(
    datasource_id: str,
    body: DatasourceConnectionPatch,
    container: ContainerDep,
) -> DatasourceConnection:
    try:
        return await container.datasource_service.patch_connection(datasource_id, body)
    except ValueError as exc:
        raise _http_400(exc) from exc


@router.delete("/datasources/{datasource_id}")
async def delete_datasource(datasource_id: str, container: ContainerDep) -> None:
    try:
        await container.datasource_service.delete_connection(datasource_id)
    except ValueError as exc:
        raise _http_400(exc) from exc


@router.post("/datasources/{datasource_id}/test", response_model=DatasourceTestResult)
async def test_datasource(
    datasource_id: str,
    container: ContainerDep,
) -> DatasourceTestResult:
    try:
        return await container.datasource_service.test(datasource_id)
    except ValueError as exc:
        raise _http_400(exc) from exc


@router.post(
    "/datasources/{datasource_id}/introspect",
    response_model=DatasourceSchemaSnapshot,
)
async def introspect_datasource(
    datasource_id: str,
    container: ContainerDep,
) -> DatasourceSchemaSnapshot:
    try:
        return await container.datasource_service.introspect(datasource_id)
    except ValueError as exc:
        raise _http_400(exc) from exc


@router.post("/datasources/{datasource_id}/query", response_model=DatasourceQueryResult)
async def query_datasource(
    datasource_id: str,
    body: DatasourceQueryRequest,
    container: ContainerDep,
) -> DatasourceQueryResult:
    try:
        return await container.datasource_service.query(
            datasource_id, body.sql, body.params
        )
    except ValueError as exc:
        raise _http_400(exc) from exc


@router.post(
    "/datasources/{datasource_id}/execute",
    response_model=DatasourceExecuteResult,
)
async def execute_datasource(
    datasource_id: str,
    body: DatasourceExecuteRequest,
    container: ContainerDep,
) -> DatasourceExecuteResult:
    try:
        return await container.datasource_service.execute(
            datasource_id, body.sql, body.params
        )
    except ValueError as exc:
        raise _http_400(exc) from exc
