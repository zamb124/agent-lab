"""
API для управления грантами доступа к entities (OpenFGA).
"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.grant_models import (
    AccessGrantResponse,
    GrantToCompanyRequest,
    GrantToUserRequest,
)
from core.context import get_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/entities/{entity_id}/grants", tags=["Entity Grants"])


@router.post("/public", response_model=AccessGrantResponse)
async def make_entity_public(
    entity_id: str,
    container: ContainerDep,
) -> AccessGrantResponse:
    ctx = get_context()
    if not ctx or not ctx.user:
        raise ValueError("Authentication required")
    return await container.access_grant_service.grant_entity_public(
        entity_id=entity_id, created_by=ctx.user.user_id
    )


@router.post("/user", response_model=AccessGrantResponse)
async def grant_to_user(
    entity_id: str,
    request: GrantToUserRequest,
    container: ContainerDep,
) -> AccessGrantResponse:
    ctx = get_context()
    if not ctx or not ctx.user:
        raise ValueError("Authentication required")
    return await container.access_grant_service.grant_entity_to_user(
        entity_id=entity_id,
        target_user_id=request.user_id,
        role=request.role,
        created_by=ctx.user.user_id,
    )


@router.post("/company", response_model=AccessGrantResponse)
async def grant_to_company(
    entity_id: str,
    request: GrantToCompanyRequest,
    container: ContainerDep,
) -> AccessGrantResponse:
    ctx = get_context()
    if not ctx or not ctx.user:
        raise ValueError("Authentication required")
    return await container.access_grant_service.grant_entity_to_company(
        entity_id=entity_id,
        target_company_id=request.company_id,
        role=request.role,
        created_by=ctx.user.user_id,
    )


@router.get("", response_model=OffsetPage[AccessGrantResponse])
async def list_grants(
    entity_id: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[AccessGrantResponse]:
    grants, total = await asyncio.gather(
        container.access_grant_service.list_grants("entity", entity_id),
        container.access_grant_service.count_grants("entity", entity_id),
    )
    page = grants[offset : offset + limit]
    return OffsetPage[AccessGrantResponse](items=page, total=total, limit=limit, offset=offset)
