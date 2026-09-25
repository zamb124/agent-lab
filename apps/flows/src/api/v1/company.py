"""Публичный enqueue init ресурсов компании."""

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.company_operations import (
    CompanyInitPayload,
    CompanyInitScheduledResponse,
    op_flows_company_init,
)
from core.context import require_context
from core.websocket import (
    raise_invalid,
)

router = APIRouter(prefix="/company", tags=["company"])


@router.post("/init")
async def init_company(
    body: CompanyInitPayload,
    di: Di,
) -> CompanyInitScheduledResponse:
    if body.company_id == "system":
        raise_invalid(ValueError("system namespace is initialized via internal bootstrap"))
    return await op_flows_company_init(
        body,
        user=require_context().user,
        di=di,
    )
