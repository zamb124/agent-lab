"""Внутренний init компании: тонкая REST-обвязка `op_crm_company_init`."""

from fastapi import APIRouter

from apps.crm.di import Di
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
    di: Di,
) -> CrmCompanyInitResponse:
    return await op_crm_company_init(
        body,
        user=require_context().user,
        di=di,
    )
