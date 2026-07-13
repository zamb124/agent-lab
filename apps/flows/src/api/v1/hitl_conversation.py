"""Operator-facing API встроенного чата HITL-задачи.

Тот же разговор сессии, что видит пользователь, доступен оператору в карточке
WorkItem(operator_handoff). flows владеет и durable-леджером, и доступом к БД
worktracker, поэтому авторизует оператора по членству в очереди / claim прямо
здесь. Realtime — push `flows/hitl_conversation/turn_appended` через
`platform:ui_events` -> WS; клиент загружает snapshot и дописывает turns по push.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import Field

from apps.flows.src.dependencies import ContainerDep
from apps.flows.src.models.hitl_conversation import ConversationSnapshot, ConversationTurn
from core.context import require_active_company, require_context
from core.logging import get_logger
from core.models import StrictBaseModel

logger = get_logger(__name__)

router = APIRouter(prefix="/hitl", tags=["hitl-conversation"])


class OperatorMessageRequest(StrictBaseModel):
    text: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)


@router.get("/{work_item_id}/conversation", response_model=ConversationSnapshot)
async def get_conversation(container: ContainerDep, work_item_id: str) -> ConversationSnapshot:
    company_id = require_active_company().company_id
    operator_user_id = require_context().user.user_id
    try:
        return await container.hitl_conversation_service.get_snapshot(
            company_id=company_id,
            work_item_id=work_item_id,
            operator_user_id=operator_user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{work_item_id}/conversation/messages", response_model=ConversationTurn)
async def send_operator_message(
    container: ContainerDep, work_item_id: str, body: OperatorMessageRequest
) -> ConversationTurn:
    company_id = require_active_company().company_id
    operator_user_id = require_context().user.user_id
    try:
        return await container.hitl_conversation_service.append_operator_message(
            company_id=company_id,
            work_item_id=work_item_id,
            operator_user_id=operator_user_id,
            text=body.text,
            idempotency_key=body.idempotency_key,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
