"""Публичный enqueue init ресурсов компании."""

from fastapi import APIRouter

from apps.flows.realtime.company_operations import (
    CompanyInitPayload,
    CompanyInitScheduledResponse,
    op_flows_company_init,
)
from apps.flows.src.dependencies import ContainerDep
from core.context import require_context
from core.websocket import (
    raise_invalid,
)

router = APIRouter(prefix="/company", tags=["company"])


@router.post("/init")
async def init_company(
    body: CompanyInitPayload,
    container: ContainerDep,
) -> CompanyInitScheduledResponse:
    if body.company_id == "system":
        raise_invalid(ValueError("System namespace инициализируется через internal bootstrap"))
    return await op_flows_company_init(
        body,
        user=require_context().user,
        container=container,
    )
