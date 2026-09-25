"""Подтверждение Lara pending-actions из embed без повторного tool-call через LLM."""

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.lara_operations import (
    LaraPendingActionApplyPayload,
    op_flows_lara_pending_actions_apply,
)
from apps.flows.src.services.lara_action_engine import LaraPendingAction
from core.context import require_context

router = APIRouter(prefix="/lara", tags=["Lara"])


@router.post("/pending-actions/apply")
async def lara_pending_actions_apply(
    body: LaraPendingActionApplyPayload,
    di: Di,
) -> LaraPendingAction:
    return await op_flows_lara_pending_actions_apply(
        body,
        user=require_context().user,
        di=di,
    )
