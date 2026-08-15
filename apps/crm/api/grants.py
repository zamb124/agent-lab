"""
API для управления грантами (общие операции, OpenFGA).
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
) -> dict[str, bool]:
    ctx = get_context()
    if not ctx or not ctx.user:
        raise HTTPException(status_code=401, detail="Authentication required")
    success = await container.access_grant_service.revoke_grant(grant_id, ctx.user.user_id)
    return {"success": success}


@router.get("/{grant_id}", response_model=AccessGrantResponse)
async def get_grant(
    grant_id: str,
    container: ContainerDep,
) -> AccessGrantResponse:
    try:
        return await container.access_grant_service.get_grant(grant_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
