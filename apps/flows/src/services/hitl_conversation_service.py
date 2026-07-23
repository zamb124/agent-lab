"""Встроенный чат HITL: тот же разговор сессии в карточке WorkItem(operator_handoff).

Источник правды разговора — `ExecutionState.messages`. Реплики оператора и
пользователя во время HITL пишутся durable-append'ом в лог сессии (не в
`WorkItemComment`) и стримятся в Redis `stream:{a2a_task_id}` через `Emitter`
(user и operator слушают live `SubscribeToTask`). Company push
`flows/hitl_conversation/turn_appended` — для канбана, не для пузырей чата.
"""

from __future__ import annotations

from a2a.helpers.proto_helpers import get_message_text
from a2a.types import Message
from a2a.types.a2a_pb2 import ROLE_USER

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
from core.a2a import mapping_from_struct
from core.clients.redis_client import RedisClient
from core.events import publish_event_to_company
from core.logging import get_logger
from core.state import ExecutionState
from core.types import JsonObject, require_json_array, require_json_object
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
    return get_message_text(message)


def _message_metadata(message: Message) -> JsonObject:
    if not message.HasField("metadata"):
        return {}
    return mapping_from_struct(message.metadata)


def _message_file_ids(message: Message) -> list[str]:
    metadata = require_json_object(_message_metadata(message), "message.metadata")
    raw = metadata.get("hitl_file_ids")
    if raw is None:
        return []
    try:
        entries = require_json_array(raw, "hitl_file_ids")
    except ValueError:
        return []
    file_ids: list[str] = []
    for entry in entries:
        if isinstance(entry, str) and entry.strip():
            file_ids.append(entry)
    return file_ids


def _turn_role(message: Message) -> ConversationTurnRole:
    metadata = _message_metadata(message)
    if metadata.get("hitl_role") == "operator":
        return ConversationTurnRole.OPERATOR
    if message.role == ROLE_USER:
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
                    file_ids=_message_file_ids(message),
                )
            )
        return turns

    async def materialize_triggering_user_content(
        self,
        *,
        company_id: str,
        work_item_id: str,
        state: ExecutionState,
        node_id: str,
    ) -> None:
        """Durable-append реплики пользователя из state.content, если её ещё нет в messages.

        На code-only путях (example_graph classifier → hitl_node) вход пользователя
        попадает в state.content, но не в state.messages; без материализации оператор
        не видит текст, с которым создалась HITL-задача.
        """
        if not isinstance(state.content, str):
            return
        clean = state.content.strip()
        if not clean:
            return
        for message in state.messages:
            if _turn_role(message) == ConversationTurnRole.USER and _message_text(message) == clean:
                return
        if state.user_id.strip() == "":
            raise ValueError("materialize_triggering_user_content: state.user_id required")
        message_id = f"hitl-user-input:{state.task_id}"
        message = build_user_message(
            clean,
            node_id,
            context_id=state.context_id,
            task_id=state.task_id,
        )
        message.message_id = message_id
        appended = await self._runtime.append_conversation_message(
            state.session_id,
            message,
            payload=ConversationMessageAppendedPayload(
                author_role="user",
                author_user_id=state.user_id,
                work_item_id=work_item_id,
                message_id=message_id,
                idempotency_key=message_id,
            ),
        )
        if appended:
            turn = await self._sync_after_append(
                WorkItemConversationRef(
                    session_id=state.session_id,
                    context_id=state.context_id,
                    flow_id=state.session_flow_id,
                    branch_id=state.branch_id,
                    a2a_task_id=state.task_id,
                ),
                message,
            )
            await self._publish_realtime(
                company_id=company_id,
                work_item_id=work_item_id,
                session_id=state.session_id,
                turn=turn,
            )

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
        if policy.conversation is not None:
            state = await self._runtime.get_state(policy.conversation.session_id)
            if state is not None:
                await self.materialize_triggering_user_content(
                    company_id=company_id,
                    work_item_id=work_item_id,
                    state=state,
                    node_id=HITL_CONVERSATION_NODE_ID,
                )
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
        file_ids: list[str] | None = None,
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
        resolved_file_ids = [fid.strip() for fid in (file_ids or []) if fid.strip()]
        if clean == "" and len(resolved_file_ids) == 0:
            raise ValueError("Пустое сообщение оператора")

        message_id = f"hitl-op:{idempotency_key}"
        message = build_operator_message(
            clean,
            HITL_CONVERSATION_NODE_ID,
            operator_user_id=operator_user_id,
            message_id=message_id,
            context_id=ref.context_id,
            task_id=ref.a2a_task_id,
            file_ids=resolved_file_ids,
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
            if clean:
                await self._stream_to_user(ref, clean, artifact_name="operator_reply")
            if resolved_file_ids:
                await self._stream_operator_files(ref, resolved_file_ids)
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
            await self._stream_to_user(ref, clean, artifact_name="user_message")
            await self._publish_realtime(
                company_id=company_id,
                work_item_id=work_item_id,
                session_id=ref.session_id,
                turn=turn,
            )
        return turn

    async def append_closing_operator_reply(
        self,
        *,
        company_id: str,
        work_item_id: str,
        operator_user_id: str,
        text: str,
        idempotency_key: str,
        file_ids: list[str] | None = None,
    ) -> ConversationTurn | None:
        """Закрывающая реплика оператора (single_reply complete / takeover complete).

        Тот же durable append + Emitter, что mid-dialog ask в takeover.
        Пустой text и пустые file_ids — no-op (None).
        """
        clean = text.strip()
        resolved_file_ids = [fid.strip() for fid in (file_ids or []) if fid.strip()]
        if clean == "" and len(resolved_file_ids) == 0:
            return None
        item = await self._work_items.get(company_id, work_item_id)
        spec = item.interaction
        if spec is None:
            raise ValueError(f"WorkItem {work_item_id!r} без interaction spec")
        if spec.mode not in (
            WorkItemInteractionMode.SINGLE_REPLY,
            WorkItemInteractionMode.TAKEOVER,
        ):
            raise ValueError(
                f"Закрывающий ответ HITL недоступен для mode={spec.mode.value!r}"
            )
        ref = build_conversation_ref(item)
        if ref is None:
            raise ValueError(f"WorkItem {work_item_id!r} без ссылки на разговор сессии")
        if not isinstance(ref.a2a_task_id, str) or not ref.a2a_task_id.strip():
            raise ValueError(f"WorkItem {work_item_id!r} без a2a_task_id для stream")

        message_id = f"hitl-op-close:{idempotency_key}"
        message = build_operator_message(
            clean,
            HITL_CONVERSATION_NODE_ID,
            operator_user_id=operator_user_id,
            message_id=message_id,
            context_id=ref.context_id,
            task_id=ref.a2a_task_id,
            file_ids=resolved_file_ids,
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
            if clean:
                await self._stream_to_user(ref, clean, artifact_name="operator_reply")
            if resolved_file_ids:
                await self._stream_operator_files(ref, resolved_file_ids)
            await self._publish_realtime(
                company_id=company_id,
                work_item_id=work_item_id,
                session_id=ref.session_id,
                turn=turn,
            )
        logger.info(
            "hitl.conversation.closing_operator_reply",
            work_item_id=work_item_id,
            session_id=ref.session_id,
            appended=appended,
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
        task_id = ref.a2a_task_id
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError(
                f"HITL stream requires a2a_task_id on conversation ref (session={ref.session_id!r})"
            )
        state = create_initial_state(
            task_id=task_id.strip(),
            context_id=ref.context_id,
            user_id="",
            session_id=ref.session_id,
            branch_id=ref.branch_id,
        )
        emitter = Emitter(self._redis, state)
        await emitter.emit_text(text, append=True, last_chunk=False, artifact_name=artifact_name)

    async def _stream_operator_files(
        self, ref: WorkItemConversationRef, file_ids: list[str]
    ) -> None:
        task_id = ref.a2a_task_id
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError(
                f"HITL stream requires a2a_task_id on conversation ref (session={ref.session_id!r})"
            )
        state = create_initial_state(
            task_id=task_id.strip(),
            context_id=ref.context_id,
            user_id="",
            session_id=ref.session_id,
            branch_id=ref.branch_id,
        )
        emitter = Emitter(self._redis, state)
        await emitter.emit_file_artifact(file_ids, artifact_name="operator_files")

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
        await publish_event_to_company(
            company_id=company_id,
            type=HITL_CONVERSATION_TURN_APPENDED,
            payload=require_json_object(event.model_dump(mode="json")),
        )


__all__ = [
    "HitlConversationService",
    "HITL_CONVERSATION_NODE_ID",
]
