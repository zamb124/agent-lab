"""Встроенный чат HITL: тот же разговор сессии в карточке WorkItem(operator_handoff).

Источник правды разговора — `ExecutionState.messages`. Реплики оператора и
пользователя во время HITL пишутся durable-append'ом в лог сессии (не в
`WorkItemComment`), стримятся конечному пользователю через `Emitter` и
публикуются в realtime-канал `conversation:{session_id}` для карточки оператора.
"""

from __future__ import annotations

from a2a.types import Message, Role, TextPart

from apps.flows.src.durable_execution import ConversationMessageAppendedPayload
from apps.flows.src.durable_execution.manager import DurableWorkflowRuntime, create_initial_state
from apps.flows.src.models.hitl_conversation import (
    HITL_CONVERSATION_TURN_APPENDED,
    ConversationSnapshot,
    ConversationTurn,
    ConversationTurnAppendedEvent,
    ConversationTurnRole,
)
from apps.flows.src.runtime.a2a_messages import build_operator_message, build_user_message
from apps.flows.src.streaming.emitter import Emitter
from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.state import ExecutionState
from core.types import require_json_object
from core.ui_events.dispatcher import publish_ui_event_to_company
from core.worktracker.models import (
    WorkItemConversationRef,
    WorkItemInteractionMode,
    WorkItemInteractionPolicy,
    build_conversation_ref,
    build_interaction_policy,
)
from core.worktracker.service import WorkItemService

logger = get_logger(__name__)

HITL_CONVERSATION_NODE_ID = "hitl_conversation"


def _message_text(message: Message) -> str:
    parts: list[str] = []
    for part in message.parts:
        root = part.root
        if isinstance(root, TextPart):
            parts.append(root.text)
    return "".join(parts)


def _turn_role(message: Message) -> ConversationTurnRole:
    metadata = message.metadata or {}
    if metadata.get("hitl_role") == "operator":
        return ConversationTurnRole.OPERATOR
    if message.role == Role.user:
        return ConversationTurnRole.USER
    if metadata.get("system") is True:
        return ConversationTurnRole.SYSTEM
    return ConversationTurnRole.AGENT


class HitlConversationService:
    """Проекция и durable-append встроенного чата HITL-задачи."""

    def __init__(
        self,
        *,
        work_item_service: WorkItemService,
        workflow_runtime: DurableWorkflowRuntime,
        redis_client: RedisClient,
    ) -> None:
        self._work_items: WorkItemService = work_item_service
        self._runtime: DurableWorkflowRuntime = workflow_runtime
        self._redis: RedisClient = redis_client

    def _project_turns(self, state: ExecutionState | None) -> list[ConversationTurn]:
        if state is None:
            return []
        turns: list[ConversationTurn] = []
        cursor = 0
        for message in state.messages:
            text = _message_text(message)
            role = _turn_role(message)
            if role == ConversationTurnRole.SYSTEM:
                continue
            cursor += 1
            turns.append(
                ConversationTurn(
                    cursor=cursor,
                    message_id=message.message_id,
                    role=role,
                    text=text,
                )
            )
        return turns

    async def get_snapshot(
        self,
        *,
        company_id: str,
        work_item_id: str,
        operator_user_id: str,
    ) -> ConversationSnapshot:
        item = await self._work_items.get(company_id, work_item_id)
        authorized = await self._work_items.operator_authorized(item, operator_user_id)
        policy = build_interaction_policy(item, operator_authorized=authorized)
        turns = await self._load_turns(policy)
        cursor = turns[-1].cursor if turns else 0
        return ConversationSnapshot(
            work_item_id=work_item_id,
            turns=turns,
            cursor=cursor,
            policy=policy,
        )

    async def _load_turns(self, policy: WorkItemInteractionPolicy) -> list[ConversationTurn]:
        if policy.conversation is None:
            return []
        state = await self._runtime.get_state(policy.conversation.session_id)
        return self._project_turns(state)

    async def append_operator_message(
        self,
        *,
        company_id: str,
        work_item_id: str,
        operator_user_id: str,
        text: str,
        idempotency_key: str,
    ) -> ConversationTurn:
        item = await self._work_items.get(company_id, work_item_id)
        if not await self._work_items.operator_authorized(item, operator_user_id):
            raise PermissionError("Нет доступа к разговору этой задачи")
        spec = item.interaction
        if spec is None or spec.mode != WorkItemInteractionMode.TAKEOVER:
            raise ValueError("Отправка сообщения доступна только в режиме takeover")
        ref = build_conversation_ref(item)
        if ref is None:
            raise ValueError(f"WorkItem {work_item_id!r} без ссылки на разговор сессии")
        clean = text.strip()
        if not clean:
            raise ValueError("Пустое сообщение оператора")

        message_id = f"hitl-op:{idempotency_key}"
        message = build_operator_message(
            clean,
            HITL_CONVERSATION_NODE_ID,
            operator_user_id=operator_user_id,
            message_id=message_id,
            context_id=ref.context_id,
            task_id=ref.a2a_task_id,
        )
        appended = await self._runtime.append_conversation_message(
            ref.session_id,
            message,
            payload=ConversationMessageAppendedPayload(
                author_role="operator",
                author_user_id=operator_user_id,
                work_item_id=work_item_id,
                message_id=message_id,
                idempotency_key=idempotency_key,
            ),
        )
        turn = await self._sync_after_append(ref, message)
        if appended:
            await self._stream_to_user(ref, clean, artifact_name="operator_reply")
            await self._publish_realtime(
                company_id=company_id,
                work_item_id=work_item_id,
                session_id=ref.session_id,
                turn=turn,
            )
        logger.info(
            "hitl.conversation.operator_message",
            work_item_id=work_item_id,
            session_id=ref.session_id,
            appended=appended,
        )
        return turn

    async def append_user_message(
        self,
        *,
        company_id: str,
        work_item_id: str,
        ref: WorkItemConversationRef,
        user_id: str,
        text: str,
        source_message_id: str,
    ) -> ConversationTurn:
        """Durable append реплики пользователя во время takeover (из A2A-канала)."""
        clean = text.strip()
        message_id = f"hitl-user:{source_message_id}"
        message = build_user_message(
            clean,
            HITL_CONVERSATION_NODE_ID,
            context_id=ref.context_id,
            task_id=ref.a2a_task_id,
        )
        message.message_id = message_id
        appended = await self._runtime.append_conversation_message(
            ref.session_id,
            message,
            payload=ConversationMessageAppendedPayload(
                author_role="user",
                author_user_id=user_id,
                work_item_id=work_item_id,
                message_id=message_id,
                idempotency_key=message_id,
            ),
        )
        turn = await self._sync_after_append(ref, message)
        if appended:
            await self._publish_realtime(
                company_id=company_id,
                work_item_id=work_item_id,
                session_id=ref.session_id,
                turn=turn,
            )
        return turn

    async def _sync_after_append(
        self, ref: WorkItemConversationRef, message: Message
    ) -> ConversationTurn:
        state = await self._runtime.get_state(ref.session_id)
        turns = self._project_turns(state)
        for turn in turns:
            if turn.message_id == message.message_id:
                return turn
        raise RuntimeError(f"appended message {message.message_id!r} not found in projection")

    async def _stream_to_user(
        self, ref: WorkItemConversationRef, text: str, *, artifact_name: str
    ) -> None:
        state = create_initial_state(
            task_id=ref.a2a_task_id or "",
            context_id=ref.context_id,
            user_id="",
            session_id=ref.session_id,
            branch_id=ref.branch_id,
        )
        emitter = Emitter(self._redis, state)
        await emitter.emit_text(text, append=True, last_chunk=False, artifact_name=artifact_name)

    async def _publish_realtime(
        self,
        *,
        company_id: str,
        work_item_id: str,
        session_id: str,
        turn: ConversationTurn,
    ) -> None:
        event = ConversationTurnAppendedEvent(
            work_item_id=work_item_id,
            session_id=session_id,
            turn=turn,
        )
        await publish_ui_event_to_company(
            company_id=company_id,
            type=HITL_CONVERSATION_TURN_APPENDED,
            payload=require_json_object(event.model_dump(mode="json")),
        )


__all__ = [
    "HitlConversationService",
    "HITL_CONVERSATION_NODE_ID",
]
