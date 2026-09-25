"""Operator-facing API встроенного чата HITL-задачи.

Тот же разговор сессии, что видит пользователь, доступен оператору в карточке
WorkItem(operator_handoff). flows владеет и durable-леджером, и доступом к БД
worktracker, поэтому авторизует оператора по членству в очереди / claim прямо
здесь. Realtime — push `flows/hitl_conversation/turn_appended` через
`platform:events` -> WS; клиент загружает snapshot и дописывает turns по push.
REST и WS RPC зовут один `op_*`. Flow UI send остаётся HTTP fetch (как A2A).
"""

from __future__ import annotations

from fastapi import APIRouter

from apps.flows.di import Di
from apps.flows.realtime.hitl_operations import (
    op_flows_hitl_conversation_get,
    op_flows_hitl_conversation_send,
)
from apps.flows.src.models.hitl_conversation import (
    ConversationSnapshot,
    ConversationTurn,
    HitlConversationWorkItemPayload,
    OperatorMessageRequest,
)
from core.context import require_context

router = APIRouter(prefix="/hitl", tags=["hitl-conversation"])


@router.get("/{work_item_id}/conversation", response_model=ConversationSnapshot)
async def get_conversation(di: Di, work_item_id: str) -> ConversationSnapshot:
    return await op_flows_hitl_conversation_get(
        HitlConversationWorkItemPayload(work_item_id=work_item_id),
        user=require_context().user,
        di=di,
    )


@router.post("/{work_item_id}/conversation/messages", response_model=ConversationTurn)
async def send_operator_message(
    di: Di, work_item_id: str, body: OperatorMessageRequest
) -> ConversationTurn:
    return await op_flows_hitl_conversation_send(
        body.model_copy(update={"work_item_id": work_item_id}),
        user=require_context().user,
        di=di,
    )
