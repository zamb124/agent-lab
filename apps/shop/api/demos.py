"""Админские маршруты demo-витрин: тонкая REST-обвязка тех же `op_*`."""

from __future__ import annotations

from fastapi import APIRouter

from apps.shop.di import Di
from apps.shop.realtime.company_operations import (
    ShopScheduledResponse,
    op_demos_seed,
)
from core.context import require_context
from core.websocket import EmptyPayload

router = APIRouter(prefix="/demos", tags=["shop-admin"])


@router.post("/seed", response_model=ShopScheduledResponse)
async def demos_seed(
    di: Di,
) -> ShopScheduledResponse:
    """Досеять эталонные витрины в активную компанию (идемпотентно)."""
    return await op_demos_seed(
        EmptyPayload(),
        user=require_context().user,
        di=di,
    )
