"""
Сводки рабочего пространства для встраиваемого ассистента Lara.
"""

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import LaraWorkspaceSummaryResponse

router = APIRouter(prefix="/workspace", tags=["Workspace"])


@router.get("/lara-summary", response_model=LaraWorkspaceSummaryResponse)
async def get_lara_workspace_summary(
    container: ContainerDep,
    namespace: str = Query(..., description="Пространство CRM"),
) -> LaraWorkspaceSummaryResponse:
    try:
        return await container.lara_workspace_service.get_lara_summary(namespace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
