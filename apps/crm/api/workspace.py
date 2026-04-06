"""
Сводки рабочего пространства для встраиваемого ассистента Lara.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.crm.dependencies import get_lara_workspace_service
from apps.crm.models.api import LaraWorkspaceSummaryResponse
from apps.crm.services.lara_workspace_service import LaraWorkspaceService

router = APIRouter(prefix="/workspace", tags=["Workspace"])


@router.get("/lara-summary", response_model=LaraWorkspaceSummaryResponse)
async def get_lara_workspace_summary(
    namespace: str = Query(..., description="Пространство CRM"),
    service: LaraWorkspaceService = Depends(get_lara_workspace_service),
) -> LaraWorkspaceSummaryResponse:
    try:
        return await service.get_lara_summary(namespace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
