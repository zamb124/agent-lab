"""REST-зеркало команд витрины консоли (`frontend/dashboard/*`)."""

from __future__ import annotations

from fastapi import APIRouter

from apps.frontend.dependencies import ContainerDep
from apps.frontend.realtime.operations import (
    DashboardStats,
    op_dashboard_stats,
)
from core.context import require_context
from core.websocket import EmptyPayload

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(container: ContainerDep) -> DashboardStats:
    return await op_dashboard_stats(EmptyPayload(), user=require_context().user, container=container)
