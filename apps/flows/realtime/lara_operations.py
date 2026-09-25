"""Lara pending-actions apply: один `op_*` для REST и WS RPC."""

from __future__ import annotations

from pydantic import Field

from apps.flows.di import Di
from apps.flows.realtime.operations import (
    require_company_member,
)
from apps.flows.src.services.lara_action_engine import LaraPendingAction
from core.models.base import StrictBaseModel
from core.models.identity_models import User
from core.websocket import (
    raise_forbidden,
    raise_invalid,
)


class LaraPendingActionApplyPayload(StrictBaseModel):
    pending_action_id: str = Field(min_length=1)
    context_id: str = Field(min_length=1)
    idempotency_key: str | None = None


async def op_flows_lara_pending_actions_apply(
    payload: LaraPendingActionApplyPayload,
    *,
    user: User,
    di: Di,
) -> LaraPendingAction:
    _ = user
    _ = await require_company_member(di)
    try:
        return await di.lara_facade.apply_pending_action_from_http(
            pending_action_id=payload.pending_action_id,
            context_id=payload.context_id,
            idempotency_key=payload.idempotency_key,
        )
    except PermissionError as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_invalid(exc)
