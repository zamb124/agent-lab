"""Datasource connections: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import TypeVar

from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.container import FlowContainer
from core.authz.errors import AuthzDenied
from core.datasources.models import (
    DatasourceConnection,
    DatasourceConnectionCreate,
    DatasourceConnectionPatchPayload,
    DatasourceConnectorSpec,
    DatasourceConnectorUpsert,
    DatasourceExecuteResult,
    DatasourceListPayload,
    DatasourceQueryResult,
    DatasourceSchemaArgs,
    DatasourceSchemaSnapshot,
    DatasourceSqlCallArgs,
    DatasourceTestResult,
)
from core.models.identity_models import User
from core.pagination import ListResponse, OffsetPage
from core.websocket import (
    EmptyPayload,
    raise_forbidden,
    raise_invalid,
)

T = TypeVar("T")


async def _datasource_call(coro: Awaitable[T]) -> T:
    try:
        return await coro
    except AuthzDenied as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_invalid(exc)


async def op_flows_datasources_connectors_list(
    payload: EmptyPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ListResponse[DatasourceConnectorSpec]:
    _ = payload
    _ = user
    _ = await require_company_member(container)
    items = await _datasource_call(container.datasource_service.list_connectors())
    return ListResponse[DatasourceConnectorSpec](items=items)


async def op_flows_datasources_connectors_upsert(
    payload: DatasourceConnectorUpsert,
    *,
    user: User,
    container: FlowContainer,
) -> DatasourceConnectorSpec:
    _ = user
    _ = await require_company_member(container)
    return await _datasource_call(container.datasource_service.upsert_connector(payload))


async def op_flows_datasources_list(
    payload: DatasourceListPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[DatasourceConnection]:
    _ = user
    _ = await require_company_member(container)
    items = await _datasource_call(container.datasource_service.list_connections())
    total = len(items)
    return OffsetPage[DatasourceConnection](
        items=items[payload.offset : payload.offset + payload.limit],
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_datasources_item(
    payload: DatasourceSchemaArgs,
    *,
    user: User,
    container: FlowContainer,
) -> DatasourceConnection:
    _ = user
    _ = await require_company_member(container)
    return await _datasource_call(
        container.datasource_service.get_connection(payload.datasource_id)
    )


async def op_flows_datasources_create(
    payload: DatasourceConnectionCreate,
    *,
    user: User,
    container: FlowContainer,
) -> DatasourceConnection:
    _ = user
    _ = await require_company_member(container)
    return await _datasource_call(container.datasource_service.create_connection(payload))


async def op_flows_datasources_update(
    payload: DatasourceConnectionPatchPayload,
    *,
    user: User,
    container: FlowContainer,
) -> DatasourceConnection:
    _ = user
    _ = await require_company_member(container)
    return await _datasource_call(
        container.datasource_service.patch_connection(payload.datasource_id, payload)
    )


async def op_flows_datasources_remove(
    payload: DatasourceSchemaArgs,
    *,
    user: User,
    container: FlowContainer,
) -> None:
    _ = user
    _ = await require_company_member(container)
    await _datasource_call(container.datasource_service.delete_connection(payload.datasource_id))


async def op_flows_datasources_test(
    payload: DatasourceSchemaArgs,
    *,
    user: User,
    container: FlowContainer,
) -> DatasourceTestResult:
    _ = user
    _ = await require_company_member(container)
    return await _datasource_call(container.datasource_service.test(payload.datasource_id))


async def op_flows_datasources_introspect(
    payload: DatasourceSchemaArgs,
    *,
    user: User,
    container: FlowContainer,
) -> DatasourceSchemaSnapshot:
    _ = user
    _ = await require_company_member(container)
    return await _datasource_call(
        container.datasource_service.introspect(payload.datasource_id)
    )


async def op_flows_datasources_query(
    payload: DatasourceSqlCallArgs,
    *,
    user: User,
    container: FlowContainer,
) -> DatasourceQueryResult:
    _ = user
    _ = await require_company_member(container)
    return await _datasource_call(
        container.datasource_service.query(payload.datasource_id, payload.sql, payload.params)
    )


async def op_flows_datasources_execute(
    payload: DatasourceSqlCallArgs,
    *,
    user: User,
    container: FlowContainer,
) -> DatasourceExecuteResult:
    _ = user
    _ = await require_company_member(container)
    return await _datasource_call(
        container.datasource_service.execute(payload.datasource_id, payload.sql, payload.params)
    )
