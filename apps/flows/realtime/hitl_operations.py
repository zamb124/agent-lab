"""HITL conversation: один `op_*` на verb для REST и WS RPC."""

from __future__ import annotations

from apps.flows.src.container import FlowContainer
from apps.flows.src.models.hitl_conversation import (
    ConversationSnapshot,
    ConversationTurn,
    HitlConversationWorkItemPayload,
    OperatorMessageRequest,
)
from core.context import require_active_company
from core.models.identity_models import User
from core.websocket import (
    raise_forbidden,
    raise_invalid,
    raise_not_found,
)


def _require_work_item_id(work_item_id: str) -> str:
    if work_item_id == "":
        raise_invalid(ValueError("work_item_id required"))
    return work_item_id


async def op_flows_hitl_conversation_get(
    payload: HitlConversationWorkItemPayload,
    *,
    user: User,
    container: FlowContainer,
) -> ConversationSnapshot:
    work_item_id = _require_work_item_id(payload.work_item_id)
    company_id = require_active_company().company_id
    try:
        return await container.hitl_conversation_service.get_snapshot(
            company_id=company_id,
            work_item_id=work_item_id,
            operator_user_id=user.user_id,
        )
    except ValueError as exc:
        raise_not_found(exc)


async def op_flows_hitl_conversation_send(
    payload: OperatorMessageRequest,
    *,
    user: User,
    container: FlowContainer,
) -> ConversationTurn:
    work_item_id = _require_work_item_id(payload.work_item_id)
    company_id = require_active_company().company_id
    try:
        return await container.hitl_conversation_service.append_operator_message(
            company_id=company_id,
            work_item_id=work_item_id,
            operator_user_id=user.user_id,
            text=payload.text,
            idempotency_key=payload.idempotency_key,
            file_ids=payload.file_ids,
        )
    except PermissionError as exc:
        raise_forbidden(exc)
    except ValueError as exc:
        raise_invalid(exc)
