"""Внутренний init компании: тонкая REST-обвязка `op_crm_company_init`."""

from fastapi import APIRouter

from apps.crm.dependencies import ContainerDep
from apps.crm.realtime.operations import (
    CrmCompanyInitPayload,
    CrmCompanyInitResponse,
    op_crm_company_init,
)
from core.context import require_context

router = APIRouter(prefix="/internal/company", tags=["CRM Company"])


@router.post("/init", response_model=CrmCompanyInitResponse)
async def init_company(
    body: CrmCompanyInitPayload,
    container: ContainerDep,
) -> CrmCompanyInitResponse:
    return await op_crm_company_init(
        body,
        user=require_context().user,
        container=container,
    )
