"""
API для управления грантами доступа к namespaces.
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.grant_models import (
    AccessGrantResponse,
    GrantToCompanyRequest,
    GrantToUserRequest,
)
from core.context import get_context
from core.pagination import OffsetPage

router = APIRouter(prefix="/namespaces/{namespace}/grants", tags=["Namespace Grants"])


@router.post("/public", response_model=AccessGrantResponse)
async def make_namespace_public(
    namespace: str,
    container: ContainerDep,
):
    """Сделать весь namespace публичным"""
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")

    grant = await container.access_grant_service.grant_namespace_public(
        namespace=namespace,
        company_id=ctx.active_company.company_id,
        created_by=ctx.user.user_id
    )

    return AccessGrantResponse.model_validate(grant)


@router.post("/user", response_model=AccessGrantResponse)
async def grant_to_user(
    namespace: str,
    request: GrantToUserRequest,
    container: ContainerDep,
):
    """Пошерить namespace конкретному user"""
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")

    grant = await container.access_grant_service.grant_namespace_to_user(
        namespace=namespace,
        company_id=ctx.active_company.company_id,
        target_user_id=request.user_id,
        role=request.role,
        created_by=ctx.user.user_id
    )

    return AccessGrantResponse.model_validate(grant)


@router.post("/company", response_model=AccessGrantResponse)
async def grant_to_company(
    namespace: str,
    request: GrantToCompanyRequest,
    container: ContainerDep,
):
    """Пошерить namespace целой компании"""
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")

    grant = await container.access_grant_service.grant_namespace_to_company(
        namespace=namespace,
        company_id=ctx.active_company.company_id,
        target_company_id=request.company_id,
        role=request.role,
        created_by=ctx.user.user_id
    )

    return AccessGrantResponse.model_validate(grant)


@router.get("", response_model=OffsetPage[AccessGrantResponse])
async def list_grants(
    namespace: str,
    container: ContainerDep,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> OffsetPage[AccessGrantResponse]:
    ctx = get_context()
    if not ctx or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")

    company_id = ctx.active_company.company_id
    grants, total = await asyncio.gather(
        container.access_grant_service.list_grants("namespace", namespace, company_id),
        container.access_grant_service.count_grants("namespace", namespace, company_id),
    )
    all_items = [AccessGrantResponse.model_validate(g) for g in grants]
    page = all_items[offset:offset + limit]
    return OffsetPage[AccessGrantResponse](items=page, total=total, limit=limit, offset=offset)
