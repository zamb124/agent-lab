"""Shared resources: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

import asyncio

from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.container import FlowContainer
from apps.flows.src.models.resource import (
    ResourceDefinition,
    ResourceDeletedResponse,
    ResourceIdPayload,
    ResourceListPayload,
    ResourceUpdatePayload,
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


async def op_flows_resources_list(
    payload: ResourceListPayload,
    *,
    user: User,
    container: FlowContainer,
) -> OffsetPage[ResourceDefinition]:
    _ = user
    _ = await require_company_member(container)
    resources, total = await asyncio.gather(
        container.resource_repository.list(limit=payload.limit, offset=payload.offset),
        container.resource_repository.count_all(),
    )
    if payload.type is not None:
        resources = [item for item in resources if item.type == payload.type]
    return OffsetPage[ResourceDefinition](
        items=resources,
        total=total,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_flows_resources_item(
    payload: ResourceIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ResourceDefinition:
    _ = user
    _ = await require_company_member(container)
    resource = await container.resource_repository.get(payload.resource_id)
    if resource is None:
        raise_not_found(LookupError("Resource not found"))
    return resource


async def op_flows_resources_create(
    payload: ResourceDefinition,
    *,
    user: User,
    container: FlowContainer,
) -> ResourceDefinition:
    _ = user
    _ = await require_company_member(container)
    try:
        _ = payload.get_typed_config()
    except ValueError as exc:
        raise_invalid(exc)
    existing = await container.resource_repository.get(payload.resource_id)
    if existing is not None:
        raise_conflict(ValueError(f"Resource '{payload.resource_id}' already exists"))
    _ = await container.resource_repository.set(payload)
    logger.info("flows.resource.created", resource_id=payload.resource_id)
    return payload


async def op_flows_resources_update(
    payload: ResourceUpdatePayload,
    *,
    user: User,
    container: FlowContainer,
) -> ResourceDefinition:
    _ = user
    _ = await require_company_member(container)
    resource = await container.resource_repository.get(payload.resource_id)
    if resource is None:
        raise_not_found(LookupError("Resource not found"))
    fields_set = payload.model_fields_set
    if "config" in fields_set and payload.config is None:
        raise_invalid(ValueError("Resource config must be a JSON object"))
    if "tags" in fields_set and payload.tags is None:
        raise_invalid(ValueError("Resource tags must be a list"))
    if "permission" in fields_set and payload.permission is None:
        raise_invalid(ValueError("Resource permission must be a list"))
    config = payload.config if "config" in fields_set else resource.config
    tags = payload.tags if "tags" in fields_set else resource.tags
    permission = payload.permission if "permission" in fields_set else resource.permission
    if config is None or tags is None or permission is None:
        raise_invalid(ValueError("Resource patch contains invalid null field"))
    updated_resource = ResourceDefinition(
        resource_id=resource.resource_id,
        type=resource.type,
        name=payload.name if "name" in fields_set else resource.name,
        description=(
            payload.description if "description" in fields_set else resource.description
        ),
        config=config,
        tags=tags,
        permission=permission,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )
    try:
        _ = updated_resource.get_typed_config()
    except ValueError as exc:
        raise_invalid(exc)
    _ = await container.resource_repository.set(updated_resource)
    logger.info("flows.resource.updated", resource_id=payload.resource_id)
    return updated_resource


async def op_flows_resources_remove(
    payload: ResourceIdPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ResourceDeletedResponse:
    _ = user
    _ = await require_company_member(container)
    deleted = await container.resource_repository.delete(payload.resource_id)
    if not deleted:
        raise_not_found(LookupError("Resource not found"))
    logger.info("flows.resource.deleted", resource_id=payload.resource_id)
    return ResourceDeletedResponse(status="deleted", resource_id=payload.resource_id)
