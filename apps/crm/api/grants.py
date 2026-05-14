"""
API для управления грантами (общие операции).
"""

from fastapi import APIRouter, HTTPException

from apps.crm.dependencies import ContainerDep
from apps.crm.models.grant_models import AccessGrantResponse
from core.context import get_context

router = APIRouter(prefix="/grants", tags=["Grants Management"])


@router.delete("/{grant_id}")
async def revoke_grant(
    grant_id: str,
    container: ContainerDep,
):
    """Отозвать grant"""
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        await container.access_grant_service.revoke_grant(grant_id, ctx.user.user_id)
        return {"success": True}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{grant_id}", response_model=AccessGrantResponse)
async def get_grant(
    grant_id: str,
    container: ContainerDep,
):
    """Получить grant по ID"""
    try:
        grant = await container.access_grant_service.get_grant(grant_id)
        return AccessGrantResponse.model_validate(grant)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
