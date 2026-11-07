"""Internal endpoints: init компании для idle_worker (signed context headers)."""

from fastapi import APIRouter

from apps.shop.di import Di
from apps.shop.realtime.company_operations import (
    ShopCompanyInitPayload,
    ShopScheduledResponse,
    op_shop_company_init,
)
from core.context import require_context

router = APIRouter(prefix="/internal/company", tags=["shop-internal"])


@router.post("/init", response_model=ShopScheduledResponse)
async def init_company(
    body: ShopCompanyInitPayload,
    di: Di,
) -> ShopScheduledResponse:
    return await op_shop_company_init(
        body,
        user=require_context().user,
        di=di,
    )
