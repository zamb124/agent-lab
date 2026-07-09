"""Internal endpoints flows для trusted service-to-service вызовов."""

from __future__ import annotations

from fastapi import APIRouter

from apps.flows.src.api.v1.company import (
    InitCompanyRequest,
    InitCompanyResponse,
    schedule_company_init,
)
from apps.flows.src.dependencies import ContainerDep

router = APIRouter(tags=["internal-company"])


@router.post("/company/init", response_model=InitCompanyResponse)
async def internal_init_company(
    container: ContainerDep,
    request: InitCompanyRequest,
) -> InitCompanyResponse:
    """Инициализация компании из idle_worker / trusted peers (signed internal headers)."""
    _ = container
    return await schedule_company_init(request)
