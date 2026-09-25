"""Trusted peer enqueue init ресурсов компании (signed internal headers)."""

from __future__ import annotations

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.company_operations import (
    CompanyInitPayload,
    CompanyInitScheduledResponse,
    op_flows_company_init,
)
from core.context import require_context

router = APIRouter(tags=["internal-company"])


@router.post("/company/init")
async def internal_init_company(
    body: CompanyInitPayload,
    di: Di,
) -> CompanyInitScheduledResponse:
    return await op_flows_company_init(
        body,
        user=require_context().user,
        di=di,
    )
