"""REST-зеркало datasource connections: path/query → тот же `op_*`, что и WS."""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.flows.realtime.datasource_operations import (
    op_flows_datasources_connectors_list,
    op_flows_datasources_connectors_upsert,
    op_flows_datasources_create,
    op_flows_datasources_execute,
    op_flows_datasources_introspect,
    op_flows_datasources_item,
    op_flows_datasources_list,
    op_flows_datasources_query,
    op_flows_datasources_remove,
    op_flows_datasources_test,
    op_flows_datasources_update,
)
from apps.flows.realtime.operations import FlowsEmptyPayload
from apps.flows.src.dependencies import ContainerDep
from core.context import require_context
from core.datasources.models import (
    DatasourceConnection,
    DatasourceConnectionCreate,
    DatasourceConnectionPatch,
    DatasourceConnectionPatchPayload,
    DatasourceConnectorSpec,
    DatasourceConnectorUpsert,
    DatasourceExecuteResult,
    DatasourceListPayload,
    DatasourceQueryResult,
    DatasourceSchemaArgs,
    DatasourceSchemaSnapshot,
    DatasourceSqlCallArgs,
    DatasourceSqlRequest,
    DatasourceTestResult,
)
from core.pagination import ListResponse, OffsetPage

router = APIRouter(tags=["datasources"])


@router.get("/datasources/connectors", response_model=ListResponse[DatasourceConnectorSpec])
async def list_datasource_connectors(
    container: ContainerDep,
) -> ListResponse[DatasourceConnectorSpec]:
    return await op_flows_datasources_connectors_list(
        FlowsEmptyPayload(),
        user=require_context().user,
        container=container,
    )


@router.put("/datasources/connectors", response_model=DatasourceConnectorSpec)
async def upsert_datasource_connector(
    body: DatasourceConnectorUpsert,
    container: ContainerDep,
) -> DatasourceConnectorSpec:
    return await op_flows_datasources_connectors_upsert(
        body,
        user=require_context().user,
        container=container,
    )


@router.get("/datasources", response_model=OffsetPage[DatasourceConnection])
async def list_datasources(
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[DatasourceConnection]:
    return await op_flows_datasources_list(
        DatasourceListPayload(limit=limit, offset=offset),
        user=require_context().user,
        container=container,
    )


@router.post("/datasources", response_model=DatasourceConnection)
async def create_datasource(
    body: DatasourceConnectionCreate, container: ContainerDep
) -> DatasourceConnection:
    return await op_flows_datasources_create(
        body, user=require_context().user, container=container
    )


@router.get("/datasources/{datasource_id}", response_model=DatasourceConnection)
async def get_datasource(datasource_id: str, container: ContainerDep) -> DatasourceConnection:
    return await op_flows_datasources_item(
        DatasourceSchemaArgs(datasource_id=datasource_id),
        user=require_context().user,
        container=container,
    )


@router.patch("/datasources/{datasource_id}", response_model=DatasourceConnection)
async def patch_datasource(
    datasource_id: str,
    body: DatasourceConnectionPatch,
    container: ContainerDep,
) -> DatasourceConnection:
    return await op_flows_datasources_update(
        DatasourceConnectionPatchPayload.model_validate(
            {"datasource_id": datasource_id, **body.model_dump(exclude_unset=True)}
        ),
        user=require_context().user,
        container=container,
    )


@router.delete("/datasources/{datasource_id}")
async def delete_datasource(datasource_id: str, container: ContainerDep) -> None:
    return await op_flows_datasources_remove(
        DatasourceSchemaArgs(datasource_id=datasource_id),
        user=require_context().user,
        container=container,
    )


@router.post("/datasources/{datasource_id}/test", response_model=DatasourceTestResult)
async def test_datasource(datasource_id: str, container: ContainerDep) -> DatasourceTestResult:
    return await op_flows_datasources_test(
        DatasourceSchemaArgs(datasource_id=datasource_id),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/datasources/{datasource_id}/introspect",
    response_model=DatasourceSchemaSnapshot,
)
async def introspect_datasource(
    datasource_id: str, container: ContainerDep
) -> DatasourceSchemaSnapshot:
    return await op_flows_datasources_introspect(
        DatasourceSchemaArgs(datasource_id=datasource_id),
        user=require_context().user,
        container=container,
    )


@router.post("/datasources/{datasource_id}/query", response_model=DatasourceQueryResult)
async def query_datasource(
    datasource_id: str,
    body: DatasourceSqlRequest,
    container: ContainerDep,
) -> DatasourceQueryResult:
    return await op_flows_datasources_query(
        DatasourceSqlCallArgs.model_validate(
            {"datasource_id": datasource_id, **body.model_dump()}
        ),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/datasources/{datasource_id}/execute",
    response_model=DatasourceExecuteResult,
)
async def execute_datasource(
    datasource_id: str,
    body: DatasourceSqlRequest,
    container: ContainerDep,
) -> DatasourceExecuteResult:
    return await op_flows_datasources_execute(
        DatasourceSqlCallArgs.model_validate(
            {"datasource_id": datasource_id, **body.model_dump()}
        ),
        user=require_context().user,
        container=container,
    )
