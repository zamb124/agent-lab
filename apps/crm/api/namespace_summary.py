"""
Сводки namespace для встраиваемого ассистента Lara.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from apps.crm.dependencies import ContainerDep
from apps.crm.models.api import LaraNamespaceSummaryResponse
from apps.crm.realtime.operations import CrmLaraSummaryPayload, op_namespaces_lara_summary
from core.context import require_context

router = APIRouter(prefix="/namespaces", tags=["CRM Namespaces"])


@router.get("/lara-summary", response_model=LaraNamespaceSummaryResponse)
async def get_lara_namespace_summary(
    container: ContainerDep,
    namespace: Annotated[str, Query(description="CRM namespace")],
) -> LaraNamespaceSummaryResponse:
    return await op_namespaces_lara_summary(
        CrmLaraSummaryPayload(namespace=namespace),
        user=require_context().user,
        container=container,
    )
