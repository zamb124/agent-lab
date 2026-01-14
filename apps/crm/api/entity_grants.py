"""
API для управления грантами доступа к entities.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException

from apps.crm.services.access_grant_service import AccessGrantService
from apps.crm.models.grant_models import GrantToUserRequest, GrantToCompanyRequest, AccessGrantResponse
from apps.crm.dependencies import get_access_grant_service
from core.context import get_context

router = APIRouter(prefix="/entities/{entity_id}/grants", tags=["Entity Grants"])


@router.post("/public", response_model=AccessGrantResponse)
async def make_entity_public(
    entity_id: str,
    service: AccessGrantService = Depends(get_access_grant_service)
):
    """Сделать entity публичной"""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        grant = await service.grant_entity_public(
            entity_id=entity_id,
            created_by=ctx.user.user_id
        )
        return AccessGrantResponse.model_validate(grant)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/user", response_model=AccessGrantResponse)
async def grant_to_user(
    entity_id: str,
    request: GrantToUserRequest,
    service: AccessGrantService = Depends(get_access_grant_service)
):
    """Пошерить entity конкретному user"""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        grant = await service.grant_entity_to_user(
            entity_id=entity_id,
            target_user_id=request.user_id,
            role=request.role,
            created_by=ctx.user.user_id
        )
        return AccessGrantResponse.model_validate(grant)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/company", response_model=AccessGrantResponse)
async def grant_to_company(
    entity_id: str,
    request: GrantToCompanyRequest,
    service: AccessGrantService = Depends(get_access_grant_service)
):
    """Пошерить entity целой компании"""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        grant = await service.grant_entity_to_company(
            entity_id=entity_id,
            target_company_id=request.company_id,
            role=request.role,
            created_by=ctx.user.user_id
        )
        return AccessGrantResponse.model_validate(grant)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("", response_model=List[AccessGrantResponse])
async def list_grants(
    entity_id: str,
    service: AccessGrantService = Depends(get_access_grant_service)
):
    """Список всех grants для entity"""
    grants = await service.list_grants("entity", entity_id)
    return [AccessGrantResponse.model_validate(g) for g in grants]

