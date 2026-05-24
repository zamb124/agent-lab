"""
API endpoints для resources.
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import ResourceDefinition, ResourceType
from core.logging import get_logger
from core.models import StrictBaseModel
from core.pagination import OffsetPage
from core.types import JsonObject

logger = get_logger(__name__)

router = APIRouter(tags=["resources"])


class ResourceUpdateRequest(StrictBaseModel):
    """Запрос на обновление ресурса"""

    name: str | None = None
    description: str | None = None
    config: JsonObject | None = None
    tags: list[str] | None = None
    permission: list[str] | None = None


@router.get("", response_model=OffsetPage[ResourceDefinition])
@router.get("/", response_model=OffsetPage[ResourceDefinition])
async def list_resources(
    container: ContainerDep,
    resource_type: Annotated[ResourceType | None, Query(alias="type")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[ResourceDefinition]:
    resources, total = await asyncio.gather(
        container.resource_repository.list(limit=limit, offset=offset),
        container.resource_repository.count_all(),
    )

    if resource_type:
        resources = [r for r in resources if r.type == resource_type]

    return OffsetPage[ResourceDefinition](
        items=resources,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{resource_id}", response_model=ResourceDefinition)
async def get_resource(
    resource_id: str,
    container: ContainerDep,
) -> ResourceDefinition:
    """Получить ресурс по ID"""
    resource = await container.resource_repository.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    return resource


@router.post("", response_model=ResourceDefinition)
@router.post("/", response_model=ResourceDefinition)
async def create_resource(
    request: ResourceDefinition,
    container: ContainerDep,
) -> ResourceDefinition:
    """Создать shared ресурс"""
    _ = request.get_typed_config()
    existing = await container.resource_repository.get(request.resource_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Resource '{request.resource_id}' already exists"
        )

    _ = await container.resource_repository.set(request)
    logger.info(f"Resource created: {request.resource_id}")

    return request


@router.put("/{resource_id}", response_model=ResourceDefinition)
async def update_resource(
    resource_id: str,
    request: ResourceUpdateRequest,
    container: ContainerDep,
) -> ResourceDefinition:
    """Обновить ресурс"""
    resource = await container.resource_repository.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    fields_set = request.model_fields_set
    if "config" in fields_set and request.config is None:
        raise HTTPException(status_code=422, detail="Resource config must be a JSON object")
    if "tags" in fields_set and request.tags is None:
        raise HTTPException(status_code=422, detail="Resource tags must be a list")
    if "permission" in fields_set and request.permission is None:
        raise HTTPException(status_code=422, detail="Resource permission must be a list")

    config = request.config if "config" in fields_set else resource.config
    tags = request.tags if "tags" in fields_set else resource.tags
    permission = request.permission if "permission" in fields_set else resource.permission
    if config is None or tags is None or permission is None:
        raise HTTPException(status_code=422, detail="Resource patch contains invalid null field")

    updated_resource = ResourceDefinition(
        resource_id=resource.resource_id,
        type=resource.type,
        name=request.name if "name" in fields_set else resource.name,
        description=(
            request.description
            if "description" in fields_set
            else resource.description
        ),
        config=config,
        tags=tags,
        permission=permission,
        created_at=resource.created_at,
        updated_at=resource.updated_at,
    )
    _ = updated_resource.get_typed_config()
    _ = await container.resource_repository.set(updated_resource)
    logger.info(f"Resource updated: {resource_id}")

    return updated_resource


@router.delete("/{resource_id}")
async def delete_resource(
    resource_id: str,
    container: ContainerDep,
) -> dict[str, str]:
    """Удалить ресурс"""
    deleted = await container.resource_repository.delete(resource_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Resource not found")

    logger.info(f"Resource deleted: {resource_id}")
    return {"status": "deleted", "resource_id": resource_id}
