"""Shared resources: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

import asyncio

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    require_company_member,
)
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
    di: Di,
) -> OffsetPage[ResourceDefinition]:
    _ = user
    _ = await require_company_member(di)
    resources, total = await asyncio.gather(
        ResourceDefinition.list(limit=payload.limit, offset=payload.offset),
        ResourceDefinition.count_all(),
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
    di: Di,
) -> ResourceDefinition:
    _ = user
    _ = await require_company_member(di)
    resource = await ResourceDefinition.get(ResourceDefinition.resource_row_id_for_active_company(payload.resource_id))
    if resource is None:
        raise_not_found(LookupError("Resource not found"))
    return resource


async def op_flows_resources_create(
    payload: ResourceDefinition,
    *,
    user: User,
    di: Di,
) -> ResourceDefinition:
    _ = user
    _ = await require_company_member(di)
    try:
        _ = payload.get_typed_config()
    except ValueError as exc:
        raise_invalid(exc)
    existing = await ResourceDefinition.get(ResourceDefinition.resource_row_id_for_active_company(payload.resource_id))
    if existing is not None:
        raise_conflict(ValueError(f"Resource '{payload.resource_id}' already exists"))
    _ = await ResourceDefinition.set(payload)
    logger.info("flows.resource.created", resource_id=payload.resource_id)
    return payload


async def op_flows_resources_update(
    payload: ResourceUpdatePayload,
    *,
    user: User,
    di: Di,
) -> ResourceDefinition:
    _ = user
    _ = await require_company_member(di)
    resource = await ResourceDefinition.get(ResourceDefinition.resource_row_id_for_active_company(payload.resource_id))
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
    _ = await ResourceDefinition.set(updated_resource)
    logger.info("flows.resource.updated", resource_id=payload.resource_id)
    return updated_resource


async def op_flows_resources_remove(
    payload: ResourceIdPayload,
    *,
    user: User,
    di: Di,
) -> ResourceDeletedResponse:
    _ = user
    _ = await require_company_member(di)
    deleted = await ResourceDefinition.delete_by_id(ResourceDefinition.resource_row_id_for_active_company(payload.resource_id))
    if not deleted:
        raise_not_found(LookupError("Resource not found"))
    logger.info("flows.resource.deleted", resource_id=payload.resource_id)
    return ResourceDeletedResponse(status="deleted", resource_id=payload.resource_id)
