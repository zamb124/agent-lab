"""
API для управления грантами доступа к namespaces.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException

from apps.crm.services.access_grant_service import AccessGrantService
from apps.crm.models.grant_models import GrantToUserRequest, GrantToCompanyRequest, AccessGrantResponse
from apps.crm.dependencies import get_access_grant_service
from core.context import get_context

router = APIRouter(prefix="/namespaces/{namespace}/grants", tags=["Namespace Grants"])


@router.post("/public", response_model=AccessGrantResponse)
async def make_namespace_public(
    namespace: str,
    service: AccessGrantService = Depends(get_access_grant_service)
):
    """Сделать весь namespace публичным"""
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    grant = await service.grant_namespace_public(
        namespace=namespace,
        company_id=ctx.active_company.company_id,
        created_by=ctx.user.user_id
    )
    
    return AccessGrantResponse.model_validate(grant)


@router.post("/user", response_model=AccessGrantResponse)
async def grant_to_user(
    namespace: str,
    request: GrantToUserRequest,
    service: AccessGrantService = Depends(get_access_grant_service)
):
    """Пошерить namespace конкретному user"""
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    grant = await service.grant_namespace_to_user(
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
    service: AccessGrantService = Depends(get_access_grant_service)
):
    """Пошерить namespace целой компании"""
    ctx = get_context()
    if not ctx or not ctx.user or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    grant = await service.grant_namespace_to_company(
        namespace=namespace,
        company_id=ctx.active_company.company_id,
        target_company_id=request.company_id,
        role=request.role,
        created_by=ctx.user.user_id
    )
    
    return AccessGrantResponse.model_validate(grant)


@router.get("", response_model=List[AccessGrantResponse])
async def list_grants(
    namespace: str,
    service: AccessGrantService = Depends(get_access_grant_service)
):
    """Список всех grants для namespace"""
    ctx = get_context()
    if not ctx or not ctx.active_company:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    grants = await service.list_grants("namespace", namespace, ctx.active_company.company_id)
    return [AccessGrantResponse.model_validate(g) for g in grants]

