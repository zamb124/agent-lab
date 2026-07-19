"""
HITL через платформенное ядро задач WorkItem.

Операторский handoff создаёт `WorkItem(kind=operator_handoff, blocking=True)` в
platform_worktracker с хуком `completed`. Диалог — durable `ExecutionState.messages`
через `HitlConversationService` + Redis `stream:{a2a_task_id}` (Emitter); user/operator
слушают live `SubscribeToTask`. На complete — closing append, затем
`process_flow_task(is_resume=True)`.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from apps.flows.config import get_settings as get_flows_settings
from apps.flows.src.models.hitl_schemas import HitlHandoffCommand, HitlInterruptSnapshot
from apps.flows.src.observability.hitl_timing import (
    maybe_record_hitl_operator_response,
    record_hitl_interrupt,
)
from apps.flows.src.services.hitl_conversation_service import HitlConversationService
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from apps.flows_worker.broker_core import broker as flows_broker
from core.clients.redis_client import RedisClient
from core.context import get_context
from core.logging import get_logger
from core.state import ExecutionState
from core.state.interrupt import HandoffMode
from core.tasks.kicker import kiq_task_name_with_context
from core.types import JsonObject, require_json_object
from core.variables.models import normalize_variables_map
from core.worktracker.models import (
    FlowSessionLink,
    QueueAssignment,
    SystemActor,
    WorkItemHook,
    WorkItemHookEvent,
    WorkItemInteractionMode,
    WorkItemInteractionSpec,
    WorkItemKind,
    WorkItemResolution,
)
from core.worktracker.service import WorkItemService

logger = get_logger(__name__)

WORK_ITEM_COMPLETED_HOOK_PATH = "/flows/api/v1/internal/work-items/completed"
HANDOFF_PREVIEW_MAX_LEN = 200

_HANDOFF_MODE_TO_INTERACTION: dict[HandoffMode, WorkItemInteractionMode] = {
    HandoffMode.SINGLE_REPLY: WorkItemInteractionMode.SINGLE_REPLY,
    HandoffMode.TAKEOVER: WorkItemInteractionMode.TAKEOVER,
}


class HitlWorkItemService:
    """Регистрация operator-handoff как WorkItem и возобновление flow по hook."""

    def __init__(
        self,
        *,
        work_item_service: WorkItemService,
        redis_client: RedisClient,
        hitl_conversation_service: HitlConversationService,
    ) -> None:
        self._work_items: WorkItemService = work_item_service
        self._redis: RedisClient = redis_client
        self._conversation: HitlConversationService = hitl_conversation_service

    async def register_handoff(
        self,
        state: ExecutionState,
        *,
        question: str,
        task_title: str,
        assignee_queue_slug: str,
        handoff_mode: HandoffMode,
        command: HitlHandoffCommand,
    ) -> tuple[UUID, str]:
        """Создаёт WorkItem operator-handoff. Возвращает (correlation_id, work_item_id)."""
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError("HitlWorkItemService.register_handoff: нужен Context с active_company")
        company_id = ctx.active_company.company_id
        slug = assignee_queue_slug.strip()
        queue = await self._work_items.get_queue_by_slug(company_id, slug)
        cid = command.correlation_id
        cid_str = str(cid)

        existing = await self._work_items.find_by_completion_correlation(company_id, cid_str)
        if existing is not None:
            return cid, existing.work_item_id

        interrupt_snapshot = HitlInterruptSnapshot(
            question=question,
            task_title=task_title,
            assignee_queue=slug,
            work_queue_id=queue.work_queue_id,
            handoff_mode=handoff_mode,
            handoff_command_id=command.idempotency_key,
            execution_branch_id=command.execution_branch_id,
            node_schedule_sequence=command.node_schedule_sequence,
            node_id=command.node_id,
            tool_call_id=command.tool_call_id,
        )
        binding: JsonObject = {
            "correlation_id": cid_str,
            "session_id": state.session_id,
            "flow_id": state.session_flow_id,
            "branch_id": state.branch_id,
            "a2a_task_id": state.task_id,
            "context_id": state.context_id,
            "end_user_id": state.user_id,
            "handoff_mode": handoff_mode.value,
            "interrupt_snapshot": require_json_object(
                interrupt_snapshot.model_dump(mode="json"), "HitlInterruptSnapshot"
            ),
            "context_data_snapshot": ctx.to_dict(),
        }
        work_item = await self._work_items.create(
            company_id=company_id,
            title=task_title,
            created_by=SystemActor(),
            description=question,
            kind=WorkItemKind.OPERATOR_HANDOFF,
            assignment=QueueAssignment(work_queue_id=queue.work_queue_id),
            blocking=True,
            interaction=WorkItemInteractionSpec(
                mode=_HANDOFF_MODE_TO_INTERACTION[handoff_mode],
            ),
            hooks=[
                WorkItemHook(
                    event=WorkItemHookEvent.COMPLETED,
                    service="flows",
                    path=WORK_ITEM_COMPLETED_HOOK_PATH,
                    binding=binding,
                ),
            ],
            links=[
                FlowSessionLink(
                    session_id=state.session_id,
                    a2a_task_id=state.task_id,
                    context_id=state.context_id,
                    flow_id=state.session_flow_id,
                    branch_id=state.branch_id,
                )
            ],
            variables=normalize_variables_map(state.variables),
            attachments=list(state.files),
        )
        logger.info(
            "hitl.work_item.registered",
            work_item_id=work_item.work_item_id,
            queue_slug=slug,
            correlation_id=cid_str,
            session_id=state.session_id,
        )
        await record_hitl_interrupt(
            self._redis,
            work_item_id=work_item.work_item_id,
        )
        return cid, work_item.work_item_id

    async def resume_from_completion(
        self,
        *,
        work_item_id: str,
        binding: JsonObject,
        resolution: WorkItemResolution,
    ) -> None:
        """Возобновляет durable workflow по завершённой operator-задаче.

        Диалог takeover уже в ExecutionState.messages; resume передаёт только
        закрывающий ответ оператора (`resolution.text`).
        """
        session_id = self._require_str(binding, "session_id")
        flow_id = self._require_str(binding, "flow_id")
        branch_id = self._require_str(binding, "branch_id")
        end_user_id = self._require_str(binding, "end_user_id")
        context_data_raw = binding.get("context_data_snapshot")
        if not isinstance(context_data_raw, dict):
            raise ValueError("binding.context_data_snapshot отсутствует, resume невозможен")
        context_data: JsonObject = context_data_raw
        channel = context_data.get("channel")
        if not isinstance(channel, str) or not channel:
            raise ValueError("context_data_snapshot не содержит строковый channel")

        a2a_task_id = binding.get("a2a_task_id")
        tid = a2a_task_id if isinstance(a2a_task_id, str) else ""
        interrupt_snapshot = binding.get("interrupt_snapshot")
        queue_slug = ""
        if isinstance(interrupt_snapshot, dict):
            raw_queue = interrupt_snapshot.get("assignee_queue")
            if isinstance(raw_queue, str):
                queue_slug = raw_queue
        await maybe_record_hitl_operator_response(
            self._redis,
            work_item_id=work_item_id,
            queue_slug=queue_slug,
            task_id=tid,
            flow_id=flow_id,
        )

        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError("resume_from_completion: нужен Context с active_company")
        company_id = ctx.active_company.company_id

        # Closing reply → durable messages + Redis stream до resume (live resubscribe).
        content = resolution.text
        resolution_file_ids: list[str] = []
        for file_ref in resolution.files:
            fid = file_ref.file_id
            if fid is not None and fid.strip():
                resolution_file_ids.append(fid.strip())
        if content.strip() or resolution_file_ids:
            item = await self._work_items.get(company_id, work_item_id)
            operator_user_id = ""
            assignment = item.assignment
            if isinstance(assignment, QueueAssignment):
                claimed = assignment.claimed_by_user_id
                if isinstance(claimed, str) and claimed.strip():
                    operator_user_id = claimed.strip()
            if operator_user_id == "":
                operator_user_id = end_user_id
            _ = await self._conversation.append_closing_operator_reply(
                company_id=company_id,
                work_item_id=work_item_id,
                operator_user_id=operator_user_id,
                text=content,
                idempotency_key=f"complete:{work_item_id}",
                file_ids=resolution_file_ids,
            )

        context_id = binding.get("context_id")
        cid = (
            context_id
            if isinstance(context_id, str) and context_id
            else session_id.split(":", 1)[-1]
        )

        resume_task = await kiq_task_name_with_context(
            TASK_PROCESS_FLOW,
            flows_broker,
            flow_id=flow_id,
            session_id=session_id,
            user_id=end_user_id,
            content=content,
            branch_id=branch_id,
            channel=channel,
            task_id=tid,
            context_id=cid,
            metadata={},
            is_resume=True,
            files=[],
            context_data=context_data,
            trace_context=None,
            background_kind="work_item_handoff",
        )
        resume_result = await asyncio.wait_for(
            resume_task.wait_result(),
            timeout=get_flows_settings().default_flow_timeout_seconds + 5,
        )
        if resume_result.is_err:
            raise RuntimeError(f"WorkItem handoff resume failed: {resume_result.error}")
        logger.info("hitl.work_item.resume_completed", session_id=session_id, flow_id=flow_id)

    @staticmethod
    def _require_str(binding: JsonObject, key: str) -> str:
        value = binding.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"binding.{key} обязателен для resume")
        return value
