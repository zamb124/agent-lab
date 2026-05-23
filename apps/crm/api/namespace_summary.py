"""
Сводки namespace для встраиваемого ассистента Lara.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import LaraNamespaceSummaryResponse

router = APIRouter(prefix="/namespaces", tags=["CRM Namespaces"])


@router.get("/lara-summary", response_model=LaraNamespaceSummaryResponse)
async def get_lara_namespace_summary(
    container: ContainerDep,
    namespace: Annotated[str, Query(description="CRM namespace")],
) -> LaraNamespaceSummaryResponse:
    try:
        return await container.lara_namespace_service.get_summary(namespace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
