"""
API для управления грантами (общие операции).
"""

from fastapi import APIRouter, Depends, HTTPException

from apps.crm.services.access_grant_service import AccessGrantService
from apps.crm.models.grant_models import AccessGrantResponse
from apps.crm.dependencies import get_access_grant_service
from core.context import get_context

router = APIRouter(prefix="/grants", tags=["Grants Management"])


@router.delete("/{grant_id}")
async def revoke_grant(
    grant_id: str,
    service: AccessGrantService = Depends(get_access_grant_service)
):
    """Отозвать grant"""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    try:
        await service.revoke_grant(grant_id, ctx.user.user_id)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{grant_id}", response_model=AccessGrantResponse)
async def get_grant(
    grant_id: str,
    service: AccessGrantService = Depends(get_access_grant_service)
):
    """Получить grant по ID"""
    try:
        grant = await service.get_grant(grant_id)
        return AccessGrantResponse.model_validate(grant)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

