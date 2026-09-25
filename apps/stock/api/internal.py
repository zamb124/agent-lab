"""Internal endpoints: init компании для idle_worker (signed context headers)."""

from fastapi import APIRouter

from apps.stock.di import Di
from apps.stock.models.api import StockCompanyInitResponse
from apps.stock.realtime.operations import (
    StockCompanyInitPayload,
    op_stock_company_init,
)
from core.context import require_context

router = APIRouter(prefix="/internal/company", tags=["stock-internal"])


@router.post("/init", response_model=StockCompanyInitResponse)
async def init_company(
    body: StockCompanyInitPayload,
    di: Di,
) -> StockCompanyInitResponse:
    return await op_stock_company_init(
        body,
        user=require_context().user,
        di=di,
    )
