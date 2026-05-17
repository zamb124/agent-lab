"""
API endpoints для resources.
"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models import ResourceDefinition, ResourceType
from apps.flows.src.models.resource import parse_typed_resource_config
from core.logging import get_logger
from core.pagination import OffsetPage

logger = get_logger(__name__)

router = APIRouter(tags=["resources"])


class ResourceCreateRequest(BaseModel):
    """Запрос на создание ресурса"""

    resource_id: str = Field(..., description="Уникальный ID ресурса")
    type: ResourceType = Field(..., description="Тип ресурса")
    name: str | None = Field(default=None, description="Название")
    description: str | None = Field(default=None, description="Описание")
    config: dict[str, Any] = Field(..., description="Конфигурация ресурса")
    tags: list[str] = Field(default_factory=list)
    permission: list[str] = Field(default_factory=list)


class ResourceUpdateRequest(BaseModel):
    """Запрос на обновление ресурса"""

    name: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    tags: list[str] | None = None
    permission: list[str] | None = None


class ResourceResponse(BaseModel):
    """Ответ с данными ресурса"""

    resource_id: str
    type: ResourceType
    name: str | None = None
    description: str | None = None
    config: dict[str, Any]
    tags: list[str] = []
    permission: list[str] = []


@router.get("", response_model=OffsetPage[ResourceResponse])
@router.get("/", response_model=OffsetPage[ResourceResponse])
async def list_resources(
    container: ContainerDep,
    type: ResourceType | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[ResourceResponse]:
    resources, total = await asyncio.gather(
        container.resource_repository.list(limit=limit, offset=offset),
        container.resource_repository.count_all(),
    )

    if type:
        resources = [r for r in resources if r.type == type]

    items = [
        ResourceResponse(
            resource_id=r.resource_id,
            type=r.type,
            name=r.name,
            description=r.description,
            config=r.config,
            tags=r.tags,
            permission=r.permission,
        )
        for r in resources
    ]
    return OffsetPage[ResourceResponse](items=items, total=total, limit=limit, offset=offset)


@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    resource_id: str,
    container: ContainerDep,
) -> ResourceResponse:
    """Получить ресурс по ID"""
    resource = await container.resource_repository.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    return ResourceResponse(
        resource_id=resource.resource_id,
        type=resource.type,
        name=resource.name,
        description=resource.description,
        config=resource.config,
        tags=resource.tags,
        permission=resource.permission,
    )


@router.post("", response_model=ResourceResponse)
@router.post("/", response_model=ResourceResponse)
async def create_resource(
    request: ResourceCreateRequest,
    container: ContainerDep,
) -> ResourceResponse:
    """Создать shared ресурс"""
    parse_typed_resource_config(request.type, request.config)
    existing = await container.resource_repository.get(request.resource_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Resource '{request.resource_id}' already exists"
        )

    resource = ResourceDefinition(
        resource_id=request.resource_id,
        type=request.type,
        name=request.name,
        description=request.description,
        config=request.config,
        tags=request.tags,
        permission=request.permission,
    )

    await container.resource_repository.set(resource)
    logger.info(f"Resource created: {resource.resource_id}")

    return ResourceResponse(
        resource_id=resource.resource_id,
        type=resource.type,
        name=resource.name,
        description=resource.description,
        config=resource.config,
        tags=resource.tags,
        permission=resource.permission,
    )


@router.put("/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: str,
    request: ResourceUpdateRequest,
    container: ContainerDep,
) -> ResourceResponse:
    """Обновить ресурс"""
    resource = await container.resource_repository.get(resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Обновляем только переданные поля
    update_data = request.model_dump(exclude_unset=True)
    resource_dict = resource.model_dump()
    resource_dict.update(update_data)
    parse_typed_resource_config(ResourceType(resource_dict["type"]), resource_dict["config"])

    updated_resource = ResourceDefinition.model_validate(resource_dict)
    await container.resource_repository.set(updated_resource)
    logger.info(f"Resource updated: {resource_id}")

    return ResourceResponse(
        resource_id=updated_resource.resource_id,
        type=updated_resource.type,
        name=updated_resource.name,
        description=updated_resource.description,
        config=updated_resource.config,
        tags=updated_resource.tags,
        permission=updated_resource.permission,
    )


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
