"""
API для управления грантами доступа к namespaces (OpenFGA).
"""

import asyncio
from typing import Annotated

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
) -> AccessGrantResponse:
    _ = (namespace, container)
    raise HTTPException(
        status_code=400,
        detail="namespace public ACL is forbidden: use entity public (user:*) instead",
    )


@router.post("/user", response_model=AccessGrantResponse)
async def grant_to_user(
    namespace: str,
    request: GrantToUserRequest,
    container: ContainerDep,
) -> AccessGrantResponse:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    return await container.access_grant_service.grant_namespace_to_user(
        namespace=namespace,
        company_id=ctx.active_company.company_id,
        target_user_id=request.user_id,
        role=request.role,
        created_by=ctx.user.user_id,
    )


@router.post("/company", response_model=AccessGrantResponse)
async def grant_to_company(
    namespace: str,
    request: GrantToCompanyRequest,
    container: ContainerDep,
) -> AccessGrantResponse:
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    return await container.access_grant_service.grant_namespace_to_company(
        namespace=namespace,
        company_id=ctx.active_company.company_id,
        target_company_id=request.company_id,
        role=request.role,
        created_by=ctx.user.user_id,
    )


@router.get("", response_model=OffsetPage[AccessGrantResponse])
async def list_grants(
    namespace: str,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OffsetPage[AccessGrantResponse]:
    ctx = get_context()
    if not ctx or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")

    company_id = ctx.active_company.company_id
    grants, total = await asyncio.gather(
        container.access_grant_service.list_grants("namespace", namespace, company_id),
        container.access_grant_service.count_grants("namespace", namespace, company_id),
    )
    page = grants[offset : offset + limit]
    return OffsetPage[AccessGrantResponse](items=page, total=total, limit=limit, offset=offset)
