"""Каталог NodeConfig: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

import asyncio

from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.node_config import (
    NodeConfig,
    NodeDeletedResponse,
    NodeIdPayload,
    NodeListPayload,
)
from core.logging import get_logger
from core.models.identity_models import User
from core.pagination import OffsetPage
from core.websocket import (
    raise_conflict,
    raise_invalid,
    raise_not_found,
)

logger = get_logger(__name__)


async def _require_catalog_tool(
    container: FlowContainer,
    tool_id: str,
    *,
    allow_node_id: str | None,
) -> None:
    if allow_node_id is not None and tool_id == allow_node_id:
        return
    tool = await container.tool_repository.get(tool_id)
    if tool is not None:
        return
    node = await container.node_repository.get(tool_id)
    if node is None:
        raise_invalid(ValueError(f"Tool '{tool_id}' not found"))


async def _require_node_tools(
    container: FlowContainer,
    node: NodeConfig,
    *,
    allow_node_id: str | None,
) -> None:
    for tool_ref in node.tools:
        await _require_catalog_tool(
            container,
            tool_ref.tool_id,
            allow_node_id=allow_node_id,
        )


async def op_flows_nodes_catalog_list(
    payload: NodeListPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[NodeConfig]:
    _ = user
    _ = await require_company_member(container)
    nodes, total = await asyncio.gather(
        container.node_repository.list(limit=payload.limit, offset=payload.offset),
        container.node_repository.count_all(),
    )
    return OffsetPage[NodeConfig](
        items=nodes,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_nodes_catalog_item(
    payload: NodeIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> NodeConfig:
    _ = user
    _ = await require_company_member(container)
    node = await container.node_repository.get(payload.node_id)
    if node is None:
        raise_not_found(LookupError("Node not found"))
    return node


async def op_flows_nodes_catalog_create(
    payload: NodeConfig,
    *,
    user: User,
    container: FlowContainer,
) -> NodeConfig:
    _ = user
    _ = await require_company_member(container)
    existing = await container.node_repository.get(payload.node_id)
    if existing is not None:
        raise_conflict(ValueError(f"Node '{payload.node_id}' already exists"))
    await _require_node_tools(container, payload, allow_node_id=None)
    _ = await container.node_repository.set(payload)
    logger.info("Node created: %s", payload.node_id)
    return payload


async def op_flows_nodes_catalog_update(
    payload: NodeConfig,
    *,
    user: User,
    container: FlowContainer,
) -> NodeConfig:
    _ = user
    _ = await require_company_member(container)
    existing = await container.node_repository.get(payload.node_id)
    if existing is None:
        raise_not_found(LookupError("Node not found"))
    await _require_node_tools(container, payload, allow_node_id=payload.node_id)
    _ = await container.node_repository.set(payload)
    logger.info("Node updated: %s", payload.node_id)
    return payload


async def op_flows_nodes_catalog_remove(
    payload: NodeIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> NodeDeletedResponse:
    _ = user
    _ = await require_company_member(container)
    deleted = await container.node_repository.delete(payload.node_id)
    if not deleted:
        raise_not_found(LookupError("Node not found"))
    logger.info("Node deleted: %s", payload.node_id)
    return NodeDeletedResponse(status="deleted", node_id=payload.node_id)
